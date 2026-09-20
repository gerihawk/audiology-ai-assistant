import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlatformAdminPage } from './PlatformAdminPage'
import { clearPlatformToken, getPlatformToken } from './tokenStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('PlatformAdminPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    clearPlatformToken()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    clearPlatformToken()
  })

  it('sin token, muestra el formulario de login; con credenciales correctas, pasa al panel de clínicas', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/platform/auth/login') {
        return Promise.resolve(
          jsonResponse({ access_token: 'token-operador', token_type: 'bearer' }),
        )
      }
      if (url.pathname === '/api/v1/platform/me') {
        return Promise.resolve(
          jsonResponse({ id: 'op-1', email: 'gerard@dev.local', display_name: 'Gerard' }),
        )
      }
      if (url.pathname === '/api/v1/platform/clinics') {
        return Promise.resolve(jsonResponse({ items: [] }))
      }
      return Promise.resolve(jsonResponse({ error: { code: 'not_found' } }, { status: 404 }))
    })
    const user = userEvent.setup()

    render(<PlatformAdminPage />)

    expect(screen.getByRole('form', { name: /iniciar sesión de operador/i })).toBeInTheDocument()

    await user.type(screen.getByLabelText(/email/i), 'gerard@dev.local')
    await user.type(screen.getByLabelText(/contraseña/i), 'correcta-y-ficticia')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(screen.getByTestId('platform-operator-summary')).toHaveTextContent('Gerard')
    })
    expect(getPlatformToken()).toBe('token-operador')
    expect(screen.getByText('Clínicas')).toBeInTheDocument()
  })

  it('muestra el error del backend con credenciales incorrectas y no persiste ningún token', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'unauthenticated', message: 'Email o contraseña incorrectos.' } },
        { status: 401 },
      ),
    )
    const user = userEvent.setup()

    render(<PlatformAdminPage />)

    await user.type(screen.getByLabelText(/email/i), 'gerard@dev.local')
    await user.type(screen.getByLabelText(/contraseña/i), 'incorrecta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email o contraseña incorrectos.')
    expect(getPlatformToken()).toBeNull()
  })

  it('un 401 posterior (token expirado a media sesión) devuelve a la pantalla de login', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/platform/me') {
        return Promise.resolve(
          jsonResponse({ id: 'op-1', email: 'gerard@dev.local', display_name: 'Gerard' }),
        )
      }
      if (url.pathname === '/api/v1/platform/clinics') {
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'unauthenticated', message: 'El token ha expirado.' } },
            { status: 401 },
          ),
        )
      }
      return Promise.resolve(jsonResponse({ error: { code: 'not_found' } }, { status: 404 }))
    })
    const { setPlatformToken } = await import('./tokenStore')
    setPlatformToken('token-a-punto-de-expirar')

    render(<PlatformAdminPage />)

    await waitFor(() => {
      expect(screen.getByRole('form', { name: /iniciar sesión de operador/i })).toBeInTheDocument()
    })
    expect(getPlatformToken()).toBeNull()
  })
})
