import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { apiRequest } from '../api/client'
import type { CurrentUser } from '../api/types'
import { clearToken, getToken, setToken, subscribe } from './tokenStore'

type Status = 'checking' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  currentUser: CurrentUser | null
  status: Status
  errorMessage: string | null
  /** Guarda el token (de `POST /api/v1/auth/login`) y resuelve el usuario
   * actual — llamado por `LoginForm` tras un login correcto. */
  signIn: (token: string) => void
  signOut: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<Status>(getToken() ? 'checking' : 'unauthenticated')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const loadCurrentUser = useCallback(() => {
    setStatus('checking')
    setErrorMessage(null)
    // Sin `devUserId`: `client.ts` adjunta `Authorization: Bearer` desde
    // el token del almacén automáticamente (VITE_AUTH_MODE=real).
    apiRequest<CurrentUser>('/api/v1/me')
      .then((user) => {
        setCurrentUser(user)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        setCurrentUser(null)
        setStatus('unauthenticated')
        setErrorMessage(error instanceof Error ? error.message : 'No se pudo verificar la sesión.')
      })
  }, [])

  // Al montar: si ya hay un token persistido (refresh de página), valida
  // la sesión contra /me en vez de asumirla válida.
  useEffect(() => {
    if (getToken()) loadCurrentUser()
  }, [loadCurrentUser])

  // `client.ts` limpia el token del almacén (fuera de React) cuando una
  // petición responde 401 — p. ej. el JWT expira a media sesión. Sin esta
  // suscripción, el estado de React se quedaría en 'authenticated' hasta
  // un remontaje (refresh de página) y cada petición nueva volvería a
  // fallar en 401 sin redirigir a login. Mismo efecto que `signOut`, pero
  // sin volver a llamar a `clearToken()` — ya está limpio, evita el bucle.
  useEffect(() => {
    return subscribe(() => {
      if (getToken() === null) {
        setCurrentUser(null)
        setErrorMessage(null)
        setStatus('unauthenticated')
      }
    })
  }, [])

  const signIn = useCallback(
    (token: string) => {
      setToken(token)
      loadCurrentUser()
    },
    [loadCurrentUser],
  )

  const signOut = useCallback(() => {
    clearToken()
    setCurrentUser(null)
    setErrorMessage(null)
    setStatus('unauthenticated')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ currentUser, status, errorMessage, signIn, signOut }),
    [currentUser, status, errorMessage, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return context
}
