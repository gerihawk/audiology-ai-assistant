import { configure, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { ClinicalSession, CurrentUser, DevUser, Patient } from './shared/api/types'
import { clearToken, setToken } from './shared/auth/tokenStore'

// Estos tests montan el árbol completo (DevUserProvider → varias páginas
// encadenadas) — más saltos async que un test de componente aislado. Con
// la suite completa en paralelo, el timeout por defecto (1000ms) es
// insuficiente bajo carga; no indica un bug de la app.
configure({ asyncUtilTimeout: 3000 })

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function notFoundResponse() {
  return jsonResponse(
    { error: { code: 'not_found', message: 'Recurso no encontrado.' } },
    { status: 404 },
  )
}

const ADMIN: DevUser = {
  id: 'u-admin',
  clinic_id: 'c-1',
  display_name: 'Alberto Admin',
  role: 'admin',
}
const CURRENT_ADMIN: CurrentUser = { ...ADMIN, email: 'admin@example.test' }

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
    created_by: 'u-admin',
    updated_by: 'u-admin',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    schema_version: 1,
    ...overrides,
  }
}

function makeSession(overrides: Partial<ClinicalSession> = {}): ClinicalSession {
  return {
    id: 's-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    professional_id: 'u-admin',
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

type Handler = (path: string, url: URL, init: RequestInit | undefined) => Response | undefined

/** Router de fetch mínimo para las pruebas de esta suite: cada test declara
 * solo los handlers que necesita; lo común (dev users, usuario actual,
 * health) se resuelve siempre igual. */
function buildFetchMock(...handlers: Handler[]) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const path = url.pathname

    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path === '/api/v1/dev/users') return Promise.resolve(jsonResponse([ADMIN]))
    if (path === '/api/v1/me') return Promise.resolve(jsonResponse(CURRENT_ADMIN))

    for (const handler of handlers) {
      const response = handler(path, url, init)
      if (response) return Promise.resolve(response)
    }

    return Promise.resolve(notFoundResponse())
  })
}

function renderAppAt(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  )
}

describe('Routing de la aplicación', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('/patients carga el listado de pacientes', async () => {
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/patients') {
          return jsonResponse({ items: [makePatient()], total: 1, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients')
    expect(await screen.findByText('PAT-0001')).toBeInTheDocument()
  })

  it('/patients/:id (montaje directo, equivalente a un reload) carga el paciente correcto', async () => {
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1')
    expect(await screen.findByText('Paciente PAT-0001')).toBeInTheDocument()
  })

  it('un id inexistente muestra el error normal sin romper la aplicación', async () => {
    vi.stubGlobal('fetch', buildFetchMock())
    renderAppAt('/patients/does-not-exist')
    expect(await screen.findByRole('alert')).toHaveTextContent(/no encontrado/i)
  })

  it('/clinical-sessions/:id carga la sesión correcta', async () => {
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/clinical-sessions/s-1') return jsonResponse(makeSession())
        if (path === '/api/v1/clinical-sessions/s-1/artifacts') {
          return jsonResponse({ items: [] })
        }
        return undefined
      }),
    )
    renderAppAt('/clinical-sessions/s-1')
    expect(await screen.findByText('Primera visita')).toBeInTheDocument()
  })

  it('crear un paciente navega a su detalle canónico', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path, _url, init) => {
        if (path === '/api/v1/patients' && init?.method === 'POST') {
          return jsonResponse(makePatient({ id: 'p-new', internal_code: 'PAT-NEW' }))
        }
        if (path === '/api/v1/patients/p-new')
          return jsonResponse(makePatient({ id: 'p-new', internal_code: 'PAT-NEW' }))
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/new')
    await user.type(await screen.findByLabelText(/código interno/i), 'PAT-NEW')
    await user.click(screen.getByRole('button', { name: /crear paciente/i }))

    expect(await screen.findByText('Paciente PAT-NEW')).toBeInTheDocument()
  })

  it('crear una sesión clínica navega a su detalle canónico', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path, _url, init) => {
        if (path === '/api/v1/patients') {
          return jsonResponse({ items: [makePatient()], total: 1, limit: 100, offset: 0 })
        }
        if (path === '/api/v1/clinical-sessions' && init?.method === 'POST') {
          return jsonResponse(makeSession({ id: 's-new', title: 'Sesión nueva' }))
        }
        if (path === '/api/v1/clinical-sessions/s-new') {
          return jsonResponse(makeSession({ id: 's-new', title: 'Sesión nueva' }))
        }
        if (path === '/api/v1/clinical-sessions/s-new/artifacts') return jsonResponse({ items: [] })
        return undefined
      }),
    )
    renderAppAt('/clinical-sessions/new')
    await screen.findByRole('option', { name: /pat-0001/i })
    await user.selectOptions(screen.getByLabelText(/paciente/i), 'p-1')
    await user.selectOptions(screen.getByLabelText(/profesional responsable/i), 'u-admin')
    await user.click(screen.getByRole('button', { name: /^crear sesión$/i }))

    expect(await screen.findByText('Sesión nueva')).toBeInTheDocument()
  })

  it('editar un paciente y cancelar vuelve a su detalle, sin depender de historial', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1')
    await user.click(await screen.findByRole('button', { name: /^editar$/i }))
    expect(await screen.findByText('Editar PAT-0001')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(await screen.findByText('Paciente PAT-0001')).toBeInTheDocument()
  })

  it('"Volver al listado" desde el detalle de paciente va a la ruta canónica /patients', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/patients') {
          return jsonResponse({ items: [makePatient()], total: 1, limit: 10, offset: 0 })
        }
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1')
    await user.click(await screen.findByRole('button', { name: /volver al listado/i }))
    expect(
      await screen.findByRole('link', { name: /ver detalle de pat-0001/i }),
    ).toBeInTheDocument()
  })

  it('la historia clínica del paciente es navegable desde su detalle', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        if (path === '/api/v1/patients/p-1/clinical-record') {
          return jsonResponse({
            patient_id: 'p-1',
            patient_internal_code: 'PAT-0001',
            patient_display_name: 'Paciente Uno',
            sessions: [],
            total: 0,
            limit: 10,
            offset: 0,
            ai_disclaimer: 'Contenido generado mediante IA.',
          })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1')
    await user.click(await screen.findByRole('link', { name: /ver historia clínica completa/i }))
    expect(await screen.findByText('Historia clínica de PAT-0001')).toBeInTheDocument()
  })

  it('restaura la página de la historia clínica desde el query param offset', async () => {
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path, url) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/patients/p-1/clinical-record') {
          expect(url.searchParams.get('offset')).toBe('10')
          return jsonResponse({
            patient_id: 'p-1',
            patient_internal_code: 'PAT-0001',
            patient_display_name: 'Paciente Uno',
            sessions: [],
            total: 15,
            limit: 10,
            offset: 10,
            ai_disclaimer: 'Contenido generado mediante IA.',
          })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1/clinical-record?offset=10')
    expect(await screen.findByText('11–15 de 15')).toBeInTheDocument()
  })

  it('/clinical-sessions/:id/ai-artifacts/:artifactId abre ese artefacto directamente (deep-link)', async () => {
    vi.stubGlobal(
      'fetch',
      buildFetchMock((path) => {
        if (path === '/api/v1/clinical-sessions/s-1') return jsonResponse(makeSession())
        if (path === '/api/v1/clinical-sessions/s-1/artifacts') return jsonResponse({ items: [] })
        if (path === '/api/v1/ai-artifacts/a-1') {
          return jsonResponse({
            id: 'a-1',
            clinical_session_id: 's-1',
            artifact_type: 'summary',
            status: 'pending_review',
            version_number: 1,
            content: { text: 'Resumen de la sesión.' },
            confidence: 0.9,
            provider_name: 'mock',
            model_name: 'mock-v1',
            schema_version: 1,
            approved_by: null,
            approved_at: null,
            rejected_by: null,
            rejected_at: null,
            rejection_reason: null,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            ai_disclaimer: 'Contenido generado mediante IA. Debe ser revisado.',
            ruleset_disclaimer: null,
          })
        }
        if (path === '/api/v1/ai-artifacts/a-1/versions') {
          return jsonResponse({
            items: [
              {
                id: 'v-1',
                version_number: 1,
                content: { text: 'Resumen de la sesión.' },
                confidence: 0.9,
                source: 'ai_generated',
                provider_name: 'mock',
                model_name: 'mock-v1',
                is_current: true,
                created_at: '2026-01-01T00:00:00Z',
              },
            ],
          })
        }
        return undefined
      }),
    )
    renderAppAt('/clinical-sessions/s-1/ai-artifacts/a-1')
    expect(await screen.findByText('Resumen de la sesión.')).toBeInTheDocument()
  })

  it('cambiar de usuario ficticio sigue funcionando con el router activo', async () => {
    const viewer: DevUser = {
      id: 'u-viewer',
      clinic_id: 'c-1',
      display_name: 'Vera Viewer',
      role: 'viewer',
    }
    const CURRENT_VIEWER: CurrentUser = { ...viewer, email: 'viewer@example.test' }
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input))
        if (url.pathname === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
        if (url.pathname === '/api/v1/dev/users')
          return Promise.resolve(jsonResponse([ADMIN, viewer]))
        if (url.pathname === '/api/v1/me') {
          const headers = init?.headers as Record<string, string> | undefined
          const requested = headers?.['X-Dev-User-Id']
          return Promise.resolve(
            jsonResponse(requested === 'u-viewer' ? CURRENT_VIEWER : CURRENT_ADMIN),
          )
        }
        if (url.pathname === '/api/v1/patients') {
          return Promise.resolve(jsonResponse({ items: [], total: 0, limit: 10, offset: 0 }))
        }
        return Promise.resolve(notFoundResponse())
      }),
    )
    renderAppAt('/patients')
    await screen.findByText(/no hay pacientes/i)
    await user.selectOptions(screen.getByLabelText(/usuario ficticio activo/i), 'u-viewer')
    await waitFor(() => {
      expect(screen.getByTestId('current-user-summary')).toHaveTextContent('Vera Viewer')
    })
  })
})

// --- VITE_AUTH_MODE=real: `RealAuthApp` no monta <DevUserProvider>, pero
// las páginas de AppRoutes llaman a useDevUser() sin condiciones — bug
// real descubierto probando manualmente en staging (pantalla en blanco,
// "useDevUser debe usarse dentro de <DevUserProvider>" al navegar a
// /patients tras hacer login). Fix: useDevUser() deriva su valor de
// useAuth() cuando no hay <DevUserProvider> — ver
// shared/devUser/DevUserContext.tsx.

const REAL_USER: CurrentUser = {
  id: 'u-real-admin',
  clinic_id: 'c-1',
  email: 'admin@example.test',
  display_name: 'Admin Real',
  role: 'admin',
}

/** Router de fetch mínimo para el modo real: sin `/api/v1/dev/users`
 * (nunca se llama en modo real) — cada test añade sus propios handlers,
 * `/health`/`/api/v1/me` siempre se resuelven igual. */
function buildRealAuthFetchMock(...handlers: Handler[]) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const path = url.pathname

    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path === '/api/v1/me') return Promise.resolve(jsonResponse(REAL_USER))

    for (const handler of handlers) {
      const response = handler(path, url, init)
      if (response) return Promise.resolve(response)
    }

    return Promise.resolve(notFoundResponse())
  })
}

describe('Routing de la aplicación — VITE_AUTH_MODE=real', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-real-1')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    clearToken()
  })

  it('/patients (reproducción exacta del bug) carga el listado sin crashear', async () => {
    vi.stubGlobal(
      'fetch',
      buildRealAuthFetchMock((path) => {
        if (path === '/api/v1/patients') {
          return jsonResponse({ items: [makePatient()], total: 1, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients')
    expect(await screen.findByText('PAT-0001')).toBeInTheDocument()
  })

  it('/patients/:id (detalle/formulario) carga el paciente correcto', async () => {
    vi.stubGlobal(
      'fetch',
      buildRealAuthFetchMock((path) => {
        if (path === '/api/v1/patients/p-1') return jsonResponse(makePatient())
        if (path === '/api/v1/clinical-sessions') {
          return jsonResponse({ items: [], total: 0, limit: 10, offset: 0 })
        }
        return undefined
      }),
    )
    renderAppAt('/patients/p-1')
    expect(await screen.findByText('Paciente PAT-0001')).toBeInTheDocument()
  })

  it('/retention (página con gating por rol) renderiza su contenido real, no el mensaje de modo fake', async () => {
    vi.stubGlobal(
      'fetch',
      buildRealAuthFetchMock((path) => {
        if (path === '/api/v1/retention/expired-audio') return jsonResponse({ items: [] })
        return undefined
      }),
    )
    renderAppAt('/retention')
    expect(await screen.findByText('Audio expirado')).toBeInTheDocument()
    expect(screen.queryByText(/selecciona un usuario de desarrollo/i)).not.toBeInTheDocument()
  })

  it('/clinical-sessions/new puebla "Profesional responsable" desde el endpoint real, no desde /api/v1/dev/users', async () => {
    // Reproducción del segundo bug encontrado (Fase 9.2, seguimiento):
    // useProfessionalOptions dependía en exclusiva de listDevUsers()
    // (GET /api/v1/dev/users), deshabilitado en producción — el
    // desplegable, campo obligatorio, llegaba siempre vacío.
    const fetchMock = buildRealAuthFetchMock((path) => {
      if (path === '/api/v1/clinical-sessions/eligible-professionals') {
        return jsonResponse([
          { id: 'u-real-admin', clinic_id: 'c-1', display_name: 'Admin Real', role: 'admin' },
        ])
      }
      if (path === '/api/v1/patients') {
        return jsonResponse({ items: [makePatient()], total: 1, limit: 100, offset: 0 })
      }
      return undefined
    })
    vi.stubGlobal('fetch', fetchMock)

    renderAppAt('/clinical-sessions/new')

    expect(await screen.findByRole('option', { name: 'Admin Real' })).toBeInTheDocument()
    const calledPaths = fetchMock.mock.calls.map(([input]) => new URL(String(input)).pathname)
    expect(calledPaths).not.toContain('/api/v1/dev/users')
  })
})
