import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from '../api/client'
import { AuthProvider, useAuth } from './AuthContext'
import { clearToken, setToken } from './tokenStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function AuthStatusProbe() {
  const { status } = useAuth()
  return <p data-testid="auth-status">{status}</p>
}

describe('AuthContext — reacciona a la limpieza de token fuera de React (Fase 9, hito 9.2)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    clearToken()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    clearToken()
  })

  it('un 401 en cualquier apiRequest posterior pasa el estado a unauthenticated sin acción del usuario', async () => {
    setToken('token-abc')
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/me') {
        return Promise.resolve(
          jsonResponse({
            id: 'u-1',
            clinic_id: 'c-1',
            email: 'admin@dev.local',
            display_name: 'Admin Ficticio',
            role: 'admin',
          }),
        )
      }
      return Promise.resolve(
        jsonResponse(
          { error: { code: 'unauthenticated', message: 'Token inválido.' } },
          { status: 401 },
        ),
      )
    })

    render(
      <AuthProvider>
        <AuthStatusProbe />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated')
    })

    // Simula cualquier otra llamada de la app (fuera de AuthContext, p. ej.
    // un feature cargando datos) recibiendo un 401 — el JWT expiró a media
    // sesión. `client.ts` limpia el token; nadie llama a `signOut` a mano.
    await expect(apiRequest('/api/v1/patients')).rejects.toThrow()

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated')
    })
  })
})
