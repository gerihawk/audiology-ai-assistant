import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Patient } from '../../shared/api/types'
import { PatientForm } from './PatientForm'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 201,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const CREATED_PATIENT: Patient = {
  id: 'p-1',
  clinic_id: 'c-1',
  internal_code: 'PAT-9999',
  display_name: null,
  birth_year: null,
  sex: null,
  preferred_language: 'es',
  notes: null,
  is_archived: false,
  created_by: 'u-1',
  updated_by: 'u-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  archived_at: null,
  schema_version: 1,
}

describe('PatientForm', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('crea un paciente y notifica onDone con el resultado', async () => {
    fetchMock.mockResolvedValue(jsonResponse(CREATED_PATIENT))

    const onDone = vi.fn()
    const user = userEvent.setup()
    render(<PatientForm devUserId="u-1" mode="create" onDone={onDone} onCancel={vi.fn()} />)

    await user.type(screen.getByLabelText(/código interno/i), 'PAT-9999')
    await user.click(screen.getByRole('button', { name: /^crear paciente$/i }))

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(CREATED_PATIENT))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/patients'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('muestra el error de conflicto asociado al campo internal_code', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message: 'Ya existe un paciente con ese código.',
            field: 'internal_code',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    render(<PatientForm devUserId="u-1" mode="create" onDone={vi.fn()} onCancel={vi.fn()} />)

    await user.type(screen.getByLabelText(/código interno/i), 'PAT-DUP')
    await user.click(screen.getByRole('button', { name: /^crear paciente$/i }))

    expect(await screen.findByText(/ya existe un paciente/i)).toBeInTheDocument()
  })

  it('el botón cancelar invoca onCancel sin llamar a la API', async () => {
    const onCancel = vi.fn()
    const user = userEvent.setup()
    render(<PatientForm devUserId="u-1" mode="create" onDone={vi.fn()} onCancel={onCancel} />)

    await user.click(screen.getByRole('button', { name: /cancelar/i }))

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
