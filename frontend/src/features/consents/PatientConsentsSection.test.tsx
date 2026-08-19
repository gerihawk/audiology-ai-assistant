import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Consent, DevUser } from '../../shared/api/types'
import { PatientConsentsSection } from './PatientConsentsSection'

const PROFESSIONALS: DevUser[] = [
  { id: 'u-audiologist', clinic_id: 'c-1', display_name: 'Ana Audióloga', role: 'audiologist' },
]

function makeConsent(overrides: Partial<Consent> = {}): Consent {
  return {
    id: 'consent-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    clinical_session_id: null,
    consent_type: 'procesamiento_ia',
    granted: true,
    consent_version: '1.0',
    granted_by: 'u-audiologist',
    recorded_at: '2026-01-01T00:00:00Z',
    notes: null,
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

describe('PatientConsentsSection', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('lista los consentimientos del paciente, filtrando por su id en la petición', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [makeConsent()] }))
    render(
      <PatientConsentsSection
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )

    expect(await screen.findByText('Procesamiento por IA')).toBeInTheDocument()
    expect(screen.getByText('Ana Audióloga')).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/patients/p-1/consents')
  })

  it('muestra un mensaje cuando no hay consentimientos registrados', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(
      <PatientConsentsSection
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )
    expect(
      await screen.findByText(/todavía no se ha registrado ningún consentimiento/i),
    ).toBeInTheDocument()
  })

  it('no renderiza nada para un viewer (sin permiso de lectura)', () => {
    const { container } = render(
      <PatientConsentsSection
        devUserId="u-viewer"
        role="viewer"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )
    expect(container).toBeEmptyDOMElement()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('oculta "Registrar consentimiento" para admin (solo audiologist puede crear)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(
      <PatientConsentsSection
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )
    await screen.findByText(/todavía no se ha registrado ningún consentimiento/i)
    expect(
      screen.queryByRole('button', { name: /registrar consentimiento/i }),
    ).not.toBeInTheDocument()
  })

  it('un audiologist puede registrar un consentimiento y la lista se refresca', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(jsonResponse(makeConsent({ id: 'consent-2', granted: false })))
      }
      return Promise.resolve(jsonResponse({ items: [] }))
    })
    const user = userEvent.setup()

    render(
      <PatientConsentsSection
        devUserId="u-audiologist"
        role="audiologist"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )

    await user.click(await screen.findByRole('button', { name: /registrar consentimiento/i }))
    await user.selectOptions(screen.getByLabelText(/^tipo \*$/i), 'grabacion_audio')
    await user.click(screen.getByRole('checkbox', { name: /otorgado/i })) // desmarcar: granted=false
    await user.click(screen.getByRole('button', { name: /^registrar$/i }))

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(postCall).toBeDefined()
    })
    const [, postInit] = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    const body = JSON.parse(postInit.body as string)
    expect(body).toEqual({ consent_type: 'grabacion_audio', granted: false, notes: null })

    // El formulario se cierra tras guardar.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /registrar consentimiento/i })).toBeInTheDocument()
    })
  })

  it('muestra el error del backend si falla el registro', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'conflict', message: 'Paciente archivado.' } },
            { status: 409 },
          ),
        )
      }
      return Promise.resolve(jsonResponse({ items: [] }))
    })
    const user = userEvent.setup()

    render(
      <PatientConsentsSection
        devUserId="u-audiologist"
        role="audiologist"
        patientId="p-1"
        professionalOptions={PROFESSIONALS}
      />,
    )

    await user.click(await screen.findByRole('button', { name: /registrar consentimiento/i }))
    await user.click(screen.getByRole('button', { name: /^registrar$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Paciente archivado.')
  })
})
