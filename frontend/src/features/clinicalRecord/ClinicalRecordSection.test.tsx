import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicalRecordPage, Patient } from '../../shared/api/types'
import { ClinicalRecordSection } from './ClinicalRecordSection'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function makePatient(overrides: Partial<Patient> = {}): Patient {
  return {
    id: 'p-1',
    clinic_id: 'c-1',
    internal_code: 'P001',
    display_name: 'Paciente Ficticio',
    birth_year: 1980,
    sex: 'unspecified',
    preferred_language: 'es',
    notes: null,
    is_archived: false,
    created_by: 'u-admin',
    updated_by: 'u-admin',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    schema_version: 1,
    ...overrides,
  }
}

function makePage(overrides: Partial<ClinicalRecordPage> = {}): ClinicalRecordPage {
  return {
    patient_id: 'p-1',
    patient_internal_code: 'P001',
    patient_display_name: 'Paciente Ficticio',
    sessions: [],
    total: 0,
    limit: 10,
    offset: 0,
    ai_disclaimer: 'Contenido generado mediante IA.',
    ...overrides,
  }
}

describe('ClinicalRecordSection', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('un viewer puede leer la historia clínica', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makePage()))
    render(
      <ClinicalRecordSection
        devUserId="u-viewer"
        role="viewer"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )
    expect(await screen.findByText(/no tiene sesiones registradas/i)).toBeInTheDocument()
  })

  it('paciente sin sesiones: estado vacío normal, no un error', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makePage({ sessions: [], total: 0 })))
    render(
      <ClinicalRecordSection
        devUserId="u-admin"
        role="admin"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )
    expect(
      await screen.findByText(/el paciente no tiene sesiones registradas/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('muestra un error si falla la carga', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'fallo' } }, { status: 500 }),
    )
    render(
      <ClinicalRecordSection
        devUserId="u-admin"
        role="admin"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('lista varias sesiones en el orden recibido del backend, con sus documentos', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        makePage({
          sessions: [
            {
              clinical_session_id: 's-1',
              session_type: 'initial_assessment',
              created_at: '2026-01-05T00:00:00Z',
              documents: [
                {
                  ai_artifact_id: 'a-1',
                  artifact_type: 'summary',
                  version_number: 1,
                  approved_by: 'u-admin',
                  approved_at: '2026-01-05T10:00:00Z',
                  content: { text: 'Resumen de la primera sesión.' },
                  is_current_baseline: false,
                  ruleset_disclaimer: null,
                },
              ],
            },
            {
              clinical_session_id: 's-2',
              session_type: 'follow_up',
              created_at: '2026-02-01T00:00:00Z',
              documents: [],
            },
          ],
          total: 2,
        }),
      ),
    )
    render(
      <ClinicalRecordSection
        devUserId="u-admin"
        role="admin"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )

    const list = await screen.findByRole('list', { name: /sesiones de la historia clínica/i })
    const sessionItems = within(list).getAllByRole('listitem')
    expect(sessionItems).toHaveLength(2)
    // Orden del backend preservado, no reordenado en frontend.
    expect(sessionItems[0]).toHaveTextContent('Valoración inicial')
    expect(sessionItems[0]).toHaveTextContent('Resumen de la primera sesión.')
    expect(sessionItems[1]).toHaveTextContent('Seguimiento')
    // Sesión con documents=[] (sin documentos aprobados) — representación
    // coherente, no se oculta la sesión ni se confunde con un error.
    expect(sessionItems[1]).toHaveTextContent(/sin documentos aprobados en esta sesión/i)
  })

  it('session_type null se presenta como "Sin especificar", solo en presentación', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        makePage({
          sessions: [
            {
              clinical_session_id: 's-1',
              session_type: null,
              created_at: '2026-01-05T00:00:00Z',
              documents: [],
            },
          ],
          total: 1,
        }),
      ),
    )
    render(
      <ClinicalRecordSection
        devUserId="u-admin"
        role="admin"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )
    expect(await screen.findByText(/sin especificar/i)).toBeInTheDocument()
  })

  it('paginación: usa total/limit/offset tal cual los devuelve el backend, sin saltar páginas', async () => {
    const sessionsPage1 = Array.from({ length: 10 }, (_, i) => ({
      clinical_session_id: `s-${i}`,
      session_type: 'follow_up' as const,
      created_at: '2026-01-01T00:00:00Z',
      documents: [],
    }))
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = new URL(String(input))
      const offset = Number(url.searchParams.get('offset'))
      if (offset === 0) {
        return jsonResponse(makePage({ sessions: sessionsPage1, total: 15, limit: 10, offset: 0 }))
      }
      return jsonResponse(
        makePage({
          sessions: [
            {
              clinical_session_id: 's-last',
              session_type: 'review' as const,
              created_at: '2026-03-01T00:00:00Z',
              documents: [],
            },
          ],
          total: 15,
          limit: 10,
          offset: 10,
        }),
      )
    })
    const user = userEvent.setup()

    render(
      <ClinicalRecordSection
        devUserId="u-admin"
        role="admin"
        patient={makePatient()}
        professionalOptions={[]}
      />,
    )

    expect(await screen.findByText('1–10 de 15')).toBeInTheDocument()
    const prevButton = screen.getByRole('button', { name: /anterior/i })
    const nextButton = screen.getByRole('button', { name: /siguiente/i })
    expect(prevButton).toBeDisabled()
    expect(nextButton).not.toBeDisabled()

    await user.click(nextButton)

    expect(await screen.findByText('11–15 de 15')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /anterior/i })).toBeEnabled())
    expect(screen.getByRole('button', { name: /siguiente/i })).toBeDisabled()
  })
})
