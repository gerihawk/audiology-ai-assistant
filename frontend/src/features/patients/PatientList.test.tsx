import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Patient } from '../../shared/api/types'
import { PatientList } from './PatientList'

function makePatient(overrides: Partial<Patient> = {}): Patient {
  return {
    id: 'p-1',
    clinic_id: 'c-1',
    internal_code: 'PAT-0001',
    display_name: 'Paciente Uno',
    birth_year: 1980,
    sex: 'female',
    preferred_language: 'es',
    notes: null,
    is_archived: false,
    created_by: 'u-1',
    updated_by: 'u-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    schema_version: 1,
    ...overrides,
  }
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('PatientList', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('muestra el estado de carga antes de recibir respuesta', () => {
    fetchMock.mockReturnValue(new Promise(() => {})) // nunca resuelve durante el test
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Cargando pacientes')
  })

  it('muestra un mensaje cuando el listado está vacío', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByText(/no hay pacientes/i)).toBeInTheDocument()
  })

  it('renderiza el listado de pacientes recibido', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makePatient()], total: 1, limit: 10, offset: 0 }),
    )
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByText('PAT-0001')).toBeInTheDocument()
    expect(screen.getByText('Paciente Uno')).toBeInTheDocument()
  })

  it('muestra un error cuando la API falla', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, { status: 500 }),
    )
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al cargar pacientes')
  })

  it('oculta "Crear paciente" para viewer y lo muestra para admin', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    const { rerender } = render(
      <PatientList
        devUserId="u-1"
        role="viewer"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText(/no hay pacientes/i)
    expect(screen.queryByRole('button', { name: /crear paciente/i })).not.toBeInTheDocument()

    rerender(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByRole('button', { name: /crear paciente/i })).toBeInTheDocument()
  })

  it('archiva un paciente tras confirmar', async () => {
    const patient = makePatient()
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input).includes('/archive')) {
        return Promise.resolve(jsonResponse({ ...patient, is_archived: true }))
      }
      return Promise.resolve(jsonResponse({ items: [patient], total: 1, limit: 10, offset: 0 }))
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const user = userEvent.setup()
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    const archiveButton = await screen.findByRole('button', { name: /archivar pat-0001/i })
    await user.click(archiveButton)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/archive'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('restaura un paciente archivado (visible solo para admin)', async () => {
    const archived = makePatient({ is_archived: true, archived_at: '2026-01-02T00:00:00Z' })
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input).includes('/restore')) {
        return Promise.resolve(jsonResponse({ ...archived, is_archived: false }))
      }
      return Promise.resolve(jsonResponse({ items: [archived], total: 1, limit: 10, offset: 0 }))
    })

    const user = userEvent.setup()
    render(
      <PatientList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    const restoreButton = await screen.findByRole('button', { name: /restaurar pat-0001/i })
    await user.click(restoreButton)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/restore'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('no ofrece restaurar a un audiologist sobre un paciente archivado', async () => {
    const archived = makePatient({ is_archived: true })
    fetchMock.mockResolvedValue(jsonResponse({ items: [archived], total: 1, limit: 10, offset: 0 }))
    render(
      <PatientList
        devUserId="u-1"
        role="audiologist"
        refreshToken={0}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText('PAT-0001')
    expect(screen.queryByRole('button', { name: /restaurar/i })).not.toBeInTheDocument()
  })
})
