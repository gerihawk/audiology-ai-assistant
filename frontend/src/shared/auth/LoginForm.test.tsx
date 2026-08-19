import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearToken } from './tokenStore'
import { AuthProvider, useAuth } from './AuthContext'
import { LoginForm } from './LoginForm'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

/** Expone `status`/`currentUser` de `AuthContext` en el DOM — así los
 * tests pueden comprobar que un login correcto de verdad hace avanzar el
 * estado de React, no solo que se llamó a `fetch`. */
function AuthStatusProbe() {
  const { status, currentUser } = useAuth()
  return (
    <p data-testid="auth-status">
      {status}:{currentUser?.email ?? ''}
    </p>
  )
}

describe('LoginForm', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    clearToken()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    clearToken()
  })

  it('con credenciales correctas, autentica y AuthContext pasa a authenticated', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/auth/login') {
        return Promise.resolve(jsonResponse({ access_token: 'token-abc', token_type: 'bearer' }))
      }
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
      return Promise.resolve(jsonResponse({ error: { code: 'not_found' } }, { status: 404 }))
    })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <AuthStatusProbe />
        <LoginForm />
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText(/email/i), 'admin@dev.local')
    await user.type(screen.getByLabelText(/contraseña/i), 'dev-ficticio-2026')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated:admin@dev.local')
    })
    const loginCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/auth/login'))!
    expect(JSON.parse(loginCall[1].body as string)).toEqual({
      email: 'admin@dev.local',
      password: 'dev-ficticio-2026',
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('muestra el error del backend con credenciales incorrectas', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'unauthenticated', message: 'Email o contraseña incorrectos.' } },
        { status: 401 },
      ),
    )
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginForm />
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText(/email/i), 'admin@dev.local')
    await user.type(screen.getByLabelText(/contraseña/i), 'incorrecta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email o contraseña incorrectos.')
  })
})
