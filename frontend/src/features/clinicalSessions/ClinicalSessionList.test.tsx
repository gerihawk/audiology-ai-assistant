import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicalSession, DevUser } from '../../shared/api/types'
import { ClinicalSessionList } from './ClinicalSessionList'

function makeSession(overrides: Partial<ClinicalSession> = {}): ClinicalSession {
  return {
    id: 's-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    professional_id: 'u-audiologist',
    session_type: 'initial_assessment',
    status: 'scheduled',
    scheduled_at: '2026-02-10T09:00:00Z',
    started_at: null,
    ended_at: null,
    title: 'Primera visita',
    administrative_notes: null,
    reviewed_by: null,
    reviewed_at: null,
    created_by: 'u-admin',
    updated_by: 'u-admin',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    schema_version: 1,
    is_archived: false,
    archived_at: null,
    ...overrides,
  }
}

const PROFESSIONALS: DevUser[] = [
  { id: 'u-audiologist', clinic_id: 'c-1', display_name: 'Ana Audióloga', role: 'audiologist' },
]

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('ClinicalSessionList', () => {
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
    fetchMock.mockReturnValue(new Promise(() => {}))
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Cargando sesiones clínicas')
  })

  it('muestra un mensaje cuando el listado está vacío', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByText(/no hay sesiones clínicas/i)).toBeInTheDocument()
  })

  it('muestra un error cuando la API falla', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, { status: 500 }),
    )
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al cargar sesiones clínicas')
  })

  it('renderiza el listado recibido con tipo, estado y profesional', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makeSession()], total: 1, limit: 10, offset: 0 }),
    )
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText('Valoración inicial')
    const row = screen.getByRole('row', { name: /valoración inicial/i })
    expect(within(row).getByText('Programada')).toBeInTheDocument()
    expect(within(row).getByText('Ana Audióloga')).toBeInTheDocument()
  })

  it('aplica los filtros de estado como parámetros de la petición', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    const user = userEvent.setup()
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText(/no hay sesiones clínicas/i)
    fetchMock.mockClear()

    await user.selectOptions(screen.getByLabelText(/^estado$/i), 'in_progress')

    await waitFor(() => {
      const [url] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
      expect(String(url)).toContain('status=in_progress')
    })
  })

  it('pagina el listado usando los botones anterior/siguiente', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makeSession()], total: 25, limit: 10, offset: 0 }),
    )
    const user = userEvent.setup()
    render(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText('Valoración inicial')
    expect(screen.getByRole('button', { name: /anterior/i })).toBeDisabled()

    fetchMock.mockClear()
    await user.click(screen.getByRole('button', { name: /siguiente/i }))

    await waitFor(() => {
      const [url] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
      expect(String(url)).toContain('offset=10')
    })
  })

  it('oculta "Crear sesión clínica" para viewer y lo muestra para admin', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    const { rerender } = render(
      <ClinicalSessionList
        devUserId="u-1"
        role="viewer"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    await screen.findByText(/no hay sesiones clínicas/i)
    expect(screen.queryByRole('button', { name: /crear sesión clínica/i })).not.toBeInTheDocument()

    rerender(
      <ClinicalSessionList
        devUserId="u-1"
        role="admin"
        refreshToken={0}
        patientOptions={[]}
        professionalOptions={PROFESSIONALS}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByRole('button', { name: /crear sesión clínica/i })).toBeInTheDocument()
  })
})
