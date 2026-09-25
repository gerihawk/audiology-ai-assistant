import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { PlatformOperator } from '../../shared/api/types'
import { getPlatformMe, platformLogout } from './api'
import { clearPlatformToken, getPlatformToken, setPlatformToken, subscribe } from './tokenStore'

/** Mismo patrón que `shared/auth/AuthContext.tsx`, pero para el operador
 * de la plataforma (Fase 14) — Context propio, almacén de token propio
 * (`./tokenStore.ts`), y `GET /api/v1/platform/me` en vez de
 * `GET /api/v1/me`. Deliberadamente sin relación de código con
 * `AuthContext`: son dos mundos de identidad separados, ver
 * `backend/app/platform_admin/service.py`. */
export type PlatformAuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

export interface PlatformAuthContextValue {
  operator: PlatformOperator | null
  status: PlatformAuthStatus
  errorMessage: string | null
  signIn: (token: string) => void
  signOut: () => void
}

const PlatformAuthContext = createContext<PlatformAuthContextValue | null>(null)

export function PlatformAuthProvider({ children }: { children: ReactNode }) {
  const [operator, setOperator] = useState<PlatformOperator | null>(null)
  const [status, setStatus] = useState<PlatformAuthStatus>(
    getPlatformToken() ? 'checking' : 'unauthenticated',
  )
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const loadOperator = useCallback(() => {
    setStatus('checking')
    setErrorMessage(null)
    getPlatformMe()
      .then((current) => {
        setOperator(current)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        setOperator(null)
        setStatus('unauthenticated')
        setErrorMessage(error instanceof Error ? error.message : 'No se pudo verificar la sesión.')
      })
  }, [])

  // Al montar: si ya hay un token persistido (refresh de página), valida
  // la sesión contra /platform/me en vez de asumirla válida.
  useEffect(() => {
    if (getPlatformToken()) loadOperator()
  }, [loadOperator])

  // `./api.ts` limpia el token del almacén (fuera de React) cuando una
  // petición responde 401 — mismo motivo que `AuthContext`: sin esto, el
  // estado se quedaría en 'authenticated' hasta un refresh de página.
  useEffect(() => {
    return subscribe(() => {
      if (getPlatformToken() === null) {
        setOperator(null)
        setErrorMessage(null)
        setStatus('unauthenticated')
      }
    })
  }, [])

  const signIn = useCallback(
    (token: string) => {
      setPlatformToken(token)
      loadOperator()
    },
    [loadOperator],
  )

  // Mismo criterio que `AuthContext.signOut` (hallazgo D1): revocar en el
  // servidor primero, limpiar el token local siempre, falle o no.
  const signOut = useCallback(() => {
    void platformLogout()
      .catch(() => undefined)
      .finally(() => {
        clearPlatformToken()
        setOperator(null)
        setErrorMessage(null)
        setStatus('unauthenticated')
      })
  }, [])

  const value = useMemo<PlatformAuthContextValue>(
    () => ({ operator, status, errorMessage, signIn, signOut }),
    [operator, status, errorMessage, signIn, signOut],
  )

  return <PlatformAuthContext.Provider value={value}>{children}</PlatformAuthContext.Provider>
}

export function usePlatformAuth(): PlatformAuthContextValue {
  const context = useContext(PlatformAuthContext)
  if (!context) {
    throw new Error('usePlatformAuth debe usarse dentro de <PlatformAuthProvider>')
  }
  return context
}
