import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlatformAuthProvider, usePlatformAuth } from './PlatformAuthContext'
import { clearPlatformToken, getPlatformToken, setPlatformToken } from './tokenStore'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function Probe() {
  const { status, signOut } = usePlatformAuth()
  return (
    <>
      <p data-testid="status">{status}</p>
      <button onClick={signOut}>Cerrar sesión</button>
    </>
  )
}

describe('PlatformAuthContext.signOut — revocación en servidor (hallazgo D1)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setPlatformToken('token-operador')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    clearPlatformToken()
  })

  async function renderAndSignOut(logoutResponse: () => Promise<Response>) {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/platform/me') {
        return Promise.resolve(
          jsonResponse({ id: 'op-1', email: 'operador@dev.local', display_name: 'Operador' }),
        )
      }
      if (url.pathname === '/api/v1/platform/auth/logout') return logoutResponse()
      throw new Error(`fetch inesperado: ${url.pathname}`)
    })
    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
    })
  }

  function logoutCall() {
    return fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith('/api/v1/platform/auth/logout'),
    ) as [RequestInfo, RequestInit] | undefined
  }

  it('llama a POST /platform/auth/logout con el token todavía presente y después lo limpia', async () => {
    await renderAndSignOut(() => Promise.resolve(new Response(null, { status: 204 })))

    const call = logoutCall()
    expect(call?.[1].method).toBe('POST')
    expect((call?.[1].headers as Record<string, string>).Authorization).toBe(
      'Bearer token-operador',
    )
    expect(getPlatformToken()).toBeNull()
  })

  it('limpia el token local aunque la llamada al servidor falle', async () => {
    await renderAndSignOut(() => Promise.reject(new TypeError('Failed to fetch')))

    expect(logoutCall()).toBeDefined()
    expect(getPlatformToken()).toBeNull()
  })
})
