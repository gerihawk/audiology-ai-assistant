import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicalSession, DevUser, Patient } from '../../shared/api/types'
import { ClinicalSessionForm } from './ClinicalSessionForm'

function makeSession(overrides: Partial<ClinicalSession> = {}): ClinicalSession {
  return {
    id: 's-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    professional_id: 'u-audiologist',
    session_type: 'initial_assessment',
    status: 'scheduled',
    scheduled_at: null,
    started_at: null,
    ended_at: null,
    title: null,
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

const PATIENT: Patient = {
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
}

const PROFESSIONALS: DevUser[] = [
  { id: 'u-audiologist', clinic_id: 'c-1', display_name: 'Ana Audióloga', role: 'audiologist' },
  { id: 'u-admin', clinic_id: 'c-1', display_name: 'Alberto Admin', role: 'admin' },
]

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 201,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('ClinicalSessionForm', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('crea una sesión clínica y notifica onDone con el resultado', async () => {
    const created = makeSession()
    fetchMock.mockResolvedValue(jsonResponse(created))
    const onDone = vi.fn()
    const user = userEvent.setup()

    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="create"
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={onDone}
        onCancel={vi.fn()}
      />,
    )

    await user.selectOptions(screen.getByLabelText(/paciente/i), 'p-1')
    await user.selectOptions(screen.getByLabelText(/profesional responsable/i), 'u-audiologist')
    await user.click(screen.getByRole('button', { name: /^crear sesión$/i }))

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(created))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/clinical-sessions'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('bloquea el doble envío mientras la petición está en curso', async () => {
    let resolveFetch: (value: Response) => void = () => {}
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const user = userEvent.setup()

    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="create"
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    await user.selectOptions(screen.getByLabelText(/paciente/i), 'p-1')
    await user.selectOptions(screen.getByLabelText(/profesional responsable/i), 'u-audiologist')
    const submitButton = screen.getByRole('button', { name: /^crear sesión$/i })
    await user.click(submitButton)
    expect(submitButton).toBeDisabled()
    await user.click(submitButton)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    resolveFetch(jsonResponse(makeSession()))
  })

  it('muestra errores de validación 422 asociados a sus campos', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'validation_error',
            message: 'Datos inválidos',
            details: [{ loc: ['body', 'title'], msg: 'Demasiado largo', type: 'value_error' }],
          },
        },
        { status: 422 },
      ),
    )
    const user = userEvent.setup()

    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="create"
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    await user.selectOptions(screen.getByLabelText(/paciente/i), 'p-1')
    await user.selectOptions(screen.getByLabelText(/profesional responsable/i), 'u-audiologist')
    await user.click(screen.getByRole('button', { name: /^crear sesión$/i }))

    expect(await screen.findByText('Demasiado largo')).toBeInTheDocument()
  })

  it('en review_pending solo permite editar título y notas administrativas', () => {
    const session = makeSession({ status: 'review_pending', title: 'Consulta' })
    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="edit"
        session={session}
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.getByLabelText(/título/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/notas administrativas/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/tipo de sesión/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/fecha y hora programada/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/paciente/i)).not.toBeInTheDocument()
  })

  it('no muestra formulario editable para una sesión reviewed', () => {
    const session = makeSession({ status: 'reviewed' })
    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="edit"
        session={session}
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(screen.getByText(/no admite edición/i)).toBeInTheDocument()
  })

  it('no muestra formulario editable para una sesión cancelled', () => {
    const session = makeSession({ status: 'cancelled' })
    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="edit"
        session={session}
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('no incluye campos de reviewed_by, reviewed_at, started_at ni ended_at', () => {
    const session = makeSession({ status: 'scheduled' })
    render(
      <ClinicalSessionForm
        devUserId="u-admin"
        mode="edit"
        session={session}
        currentUserId="u-admin"
        role="admin"
        patientOptions={[PATIENT]}
        professionalOptions={PROFESSIONALS}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText(/revisad/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/iniciad/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/finalizad/i)).not.toBeInTheDocument()
  })
})
