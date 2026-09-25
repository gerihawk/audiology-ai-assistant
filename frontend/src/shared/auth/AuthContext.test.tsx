import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from '../api/client'
import { AuthProvider, useAuth } from './AuthContext'
import { clearToken, getToken, setToken } from './tokenStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function AuthStatusProbe() {
  const { status, signOut } = useAuth()
  return (
    <>
      <p data-testid="auth-status">{status}</p>
      <button onClick={signOut}>Cerrar sesión</button>
    </>
  )
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

describe('AuthContext.signOut — revocación en servidor (hallazgo D1)', () => {
  const fetchMock = vi.fn()
  const me = {
    id: 'u-1',
    clinic_id: 'c-1',
    email: 'admin@dev.local',
    display_name: 'Admin Ficticio',
    role: 'admin',
  }

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    clearToken()
  })

  async function renderAndSignOut(logoutResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/me') return Promise.resolve(jsonResponse(me))
      if (url.pathname === '/api/v1/auth/logout') return logoutResponse()
      throw new Error(`fetch inesperado: ${url.pathname}`)
    })
    render(
      <AuthProvider>
        <AuthStatusProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated')
    })
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated')
    })
  }

  function logoutCall() {
    return fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/v1/auth/logout')) as
      [RequestInfo, RequestInit] | undefined
  }

  it('llama a POST /auth/logout con el token todavía presente y después lo limpia', async () => {
    await renderAndSignOut(() => Promise.resolve(new Response(null, { status: 204 })))

    const call = logoutCall()
    expect(call?.[1].method).toBe('POST')
    expect((call?.[1].headers as Record<string, string>).Authorization).toBe('Bearer token-abc')
    expect(getToken()).toBeNull()
  })

  it('limpia el token local aunque la llamada al servidor falle', async () => {
    await renderAndSignOut(() => Promise.reject(new TypeError('Failed to fetch')))

    expect(logoutCall()).toBeDefined()
    expect(getToken()).toBeNull()
  })
})
