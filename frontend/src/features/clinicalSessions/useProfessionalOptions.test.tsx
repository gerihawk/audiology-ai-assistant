import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../shared/auth/AuthContext'
import { clearToken, setToken } from '../../shared/auth/tokenStore'
import { DevUserProvider } from '../../shared/devUser/DevUserContext'
import type { CurrentUser } from '../../shared/api/types'
import { useProfessionalOptions } from './useProfessionalOptions'

/** Cubre el bug real de producción: `useProfessionalOptions` dependía
 * únicamente de `listDevUsers()` (GET /api/v1/dev/users), deshabilitado
 * en producción — el desplegable de "profesional responsable" llegaba
 * siempre vacío para un usuario real, un campo obligatorio al crear una
 * sesión clínica. */

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const REAL_USER: CurrentUser = {
  id: 'u-real-1',
  clinic_id: 'c-1',
  email: 'real@example.test',
  display_name: 'Usuario Real',
  role: 'admin',
}

describe('useProfessionalOptions', () => {
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

  it('modo fake: sigue llamando a /api/v1/dev/users (sin cambios)', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/dev/users') {
        return Promise.resolve(
          jsonResponse([
            { id: 'u-1', clinic_id: 'c-1', display_name: 'Admin', role: 'admin' },
            { id: 'u-2', clinic_id: 'c-1', display_name: 'Viewer', role: 'viewer' },
          ]),
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

    const wrapper = ({ children }: { children: ReactNode }) => (
      <DevUserProvider>{children}</DevUserProvider>
    )
    const currentUser: CurrentUser = {
      id: 'u-1',
      clinic_id: 'c-1',
      email: 'admin@dev.local',
      display_name: 'Admin',
      role: 'admin',
    }
    const { result } = renderHook(() => useProfessionalOptions(currentUser), { wrapper })

    await waitFor(() => expect(result.current).toHaveLength(1))
    expect(result.current[0].display_name).toBe('Admin')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/dev/users'),
      expect.anything(),
    )
  })

  it('modo real: llama al endpoint real de profesionales elegibles, no a /api/v1/dev/users', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-real')
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      if (url.pathname === '/api/v1/me') return Promise.resolve(jsonResponse(REAL_USER))
      if (url.pathname === '/api/v1/clinical-sessions/eligible-professionals') {
        return Promise.resolve(
          jsonResponse([
            { id: 'u-real-1', clinic_id: 'c-1', display_name: 'Usuario Real', role: 'admin' },
          ]),
        )
      }
      return Promise.resolve(jsonResponse({}, { status: 404 }))
    })

    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    )
    const { result } = renderHook(() => useProfessionalOptions(REAL_USER), { wrapper })

    await waitFor(() => expect(result.current).toHaveLength(1))
    expect(result.current[0].display_name).toBe('Usuario Real')
    const calledPaths = fetchMock.mock.calls.map(([input]) => new URL(String(input)).pathname)
    expect(calledPaths).not.toContain('/api/v1/dev/users')
    expect(calledPaths).toContain('/api/v1/clinical-sessions/eligible-professionals')
  })
})
