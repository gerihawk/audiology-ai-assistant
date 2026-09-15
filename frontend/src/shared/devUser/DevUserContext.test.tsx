import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { clearToken, setToken } from '../auth/tokenStore'
import { DevUserProvider, useDevUser } from './DevUserContext'

/** Cubre el bug real de producción (Fase 9, hito 9.2, revisión posterior):
 * `useDevUser()` se llama sin condiciones desde las páginas de
 * `AppRoutes` (PatientsPage, ClinicalSessionsPage, IntegrationsPage...),
 * pero `RealAuthApp` (VITE_AUTH_MODE=real) nunca monta
 * `<DevUserProvider>` — sin el fallback a `useAuthOptional()`, esto
 * crasheaba con pantalla en blanco en cuanto un usuario real navegaba a
 * cualquiera de esas páginas. */

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function Probe() {
  const { currentUser, selectedUserId, status } = useDevUser()
  return (
    <div>
      <p data-testid="status">{status}</p>
      <p data-testid="selected-user-id">{selectedUserId ?? 'null'}</p>
      <p data-testid="role">{currentUser?.role ?? 'null'}</p>
    </div>
  )
}

function ThrowProbe() {
  useDevUser()
  return null
}

describe('useDevUser', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
    clearToken()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    clearToken()
  })

  it('dentro de DevUserProvider (modo fake), su comportamiento no cambia', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/dev/users') {
        return Promise.resolve(
          jsonResponse([{ id: 'u-1', clinic_id: 'c-1', display_name: 'Admin', role: 'admin' }]),
        )
      }
      if (url.pathname === '/api/v1/me') {
        return Promise.resolve(
          jsonResponse({
            id: 'u-1',
            clinic_id: 'c-1',
            email: 'admin@dev.local',
            display_name: 'Admin',
            role: 'admin',
          }),
        )
      }
      return Promise.resolve(jsonResponse({}, { status: 404 }))
    })

    render(
      <DevUserProvider>
        <Probe />
      </DevUserProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'))
    expect(screen.getByTestId('selected-user-id')).toHaveTextContent('u-1')
    expect(screen.getByTestId('role')).toHaveTextContent('admin')
  })

  it('sin DevUserProvider pero dentro de AuthProvider (modo real), deriva el valor del usuario autenticado', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/me') {
        return Promise.resolve(
          jsonResponse({
            id: 'u-real-1',
            clinic_id: 'c-1',
            email: 'real@example.test',
            display_name: 'Usuario Real',
            role: 'audiologist',
          }),
        )
      }
      return Promise.resolve(jsonResponse({}, { status: 404 }))
    })

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    // status: 'authenticated' -> 'ready'.
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'))
    // selectedUserId se deriva de currentUser.id, no de un selector propio.
    expect(screen.getByTestId('selected-user-id')).toHaveTextContent('u-real-1')
    // `role` presente: lo necesitan páginas con gating de permisos como
    // IntegrationsPage/RetentionPage.
    expect(screen.getByTestId('role')).toHaveTextContent('audiologist')
  })

  it('mapea "checking" (validando token) a "loading" mientras /me no ha resuelto', () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
    fetchMock.mockImplementation(() => new Promise(() => {})) // nunca resuelve

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    expect(screen.getByTestId('status')).toHaveTextContent('loading')
  })

  it('mapea "unauthenticated" (token inválido) a "error"', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-invalido')
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(
          { error: { code: 'unauthenticated', message: 'Token inválido.' } },
          { status: 401 },
        ),
      ),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'))
  })

  it('lanza si no hay ni DevUserProvider ni AuthProvider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ThrowProbe />)).toThrow(
      'useDevUser debe usarse dentro de <DevUserProvider> (modo fake) o <AuthProvider> (modo real)',
    )
    consoleError.mockRestore()
  })
})
