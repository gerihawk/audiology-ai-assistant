import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import type { ClinicalSession, DevUser, Patient } from '../../shared/api/types'
import { PatientClinicalSessionsSection } from './PatientClinicalSessionsSection'

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
]

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

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('PatientClinicalSessionsSection', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('lista solo las sesiones del paciente y filtra por patient_id en la petición', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makeSession()], total: 1, limit: 10, offset: 0 }),
    )
    renderWithRouter(
      <PatientClinicalSessionsSection
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        patient={PATIENT}
        professionalOptions={PROFESSIONALS}
      />,
    )

    await screen.findByText('Valoración inicial')
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('patient_id=p-1')
  })

  it('no ofrece el selector de paciente en los filtros (paciente fijo)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    renderWithRouter(
      <PatientClinicalSessionsSection
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        patient={PATIENT}
        professionalOptions={PROFESSIONALS}
      />,
    )
    await screen.findByText(/no hay sesiones clínicas/i)
    expect(screen.queryByLabelText(/^paciente$/i)).not.toBeInTheDocument()
  })

  it('muestra "Crear sesión clínica" y enlaza al detalle con la URL canónica de la sesión', async () => {
    const session = makeSession()
    fetchMock.mockResolvedValue(jsonResponse({ items: [session], total: 1, limit: 10, offset: 0 }))

    renderWithRouter(
      <PatientClinicalSessionsSection
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        patient={PATIENT}
        professionalOptions={PROFESSIONALS}
      />,
    )

    expect(await screen.findByRole('button', { name: /crear sesión clínica/i })).toBeInTheDocument()

    const link = screen.getByRole('link', { name: /ver detalle/i })
    expect(link).toHaveAttribute('href', '/clinical-sessions/s-1')
  })

  it('oculta "Crear sesión clínica" para un viewer', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
    renderWithRouter(
      <PatientClinicalSessionsSection
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        patient={PATIENT}
        professionalOptions={PROFESSIONALS}
      />,
    )
    await screen.findByText(/no hay sesiones clínicas/i)
    expect(screen.queryByRole('button', { name: /crear sesión clínica/i })).not.toBeInTheDocument()
  })

  it('vuelve al listado y refresca los datos tras crear una sesión', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(jsonResponse(makeSession({ id: 's-2', title: 'Nueva sesión' })))
      }
      return Promise.resolve(
        jsonResponse({ items: [makeSession()], total: 1, limit: 10, offset: 0 }),
      )
    })
    const user = userEvent.setup()

    renderWithRouter(
      <PatientClinicalSessionsSection
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        patient={PATIENT}
        professionalOptions={PROFESSIONALS}
      />,
    )

    await user.click(await screen.findByRole('button', { name: /crear sesión clínica/i }))
    await user.selectOptions(screen.getByLabelText(/profesional responsable/i), 'u-audiologist')
    await user.click(screen.getByRole('button', { name: /^crear sesión$/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /crear sesión clínica/i })).toBeInTheDocument()
    })
  })
})
