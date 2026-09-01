import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { type AuthContextValue, type AuthStatus, useAuthOptional } from '../auth/AuthContext'
import { getCurrentUser, listDevUsers } from '../api/devUsers'
import type { CurrentUser, DevUser } from '../api/types'

const STORAGE_KEY = 'audiology.devUserId'

type Status = 'loading' | 'ready' | 'error'

interface DevUserContextValue {
  devUsers: DevUser[]
  currentUser: CurrentUser | null
  selectedUserId: string | null
  status: Status
  errorMessage: string | null
  selectUser: (id: string) => void
}

const DevUserContext = createContext<DevUserContextValue | null>(null)

function readStoredUserId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function DevUserProvider({ children }: { children: ReactNode }) {
  const [devUsers, setDevUsers] = useState<DevUser[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string | null>(readStoredUserId)
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    listDevUsers()
      .then((users) => {
        if (cancelled) return
        setDevUsers(users)
        setStatus('ready')
        setSelectedUserId((current) => {
          if (current && users.some((user) => user.id === current)) return current
          return users[0]?.id ?? null
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'No se pudo cargar la lista de usuarios de desarrollo.',
        )
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedUserId) {
      setCurrentUser(null)
      return
    }
    try {
      localStorage.setItem(STORAGE_KEY, selectedUserId)
    } catch {
      // localStorage no disponible (p. ej. modo privado); no es crítico.
    }

    let cancelled = false
    getCurrentUser(selectedUserId)
      .then((user) => {
        if (!cancelled) setCurrentUser(user)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error ? error.message : 'No se pudo resolver el usuario actual.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [selectedUserId])

  const value = useMemo<DevUserContextValue>(
    () => ({
      devUsers,
      currentUser,
      selectedUserId,
      status,
      errorMessage,
      selectUser: setSelectedUserId,
    }),
    [devUsers, currentUser, selectedUserId, status, errorMessage],
  )

  return <DevUserContext.Provider value={value}>{children}</DevUserContext.Provider>
}

/** `AuthContext.status` ('checking'/'authenticated'/'unauthenticated') al
 * vocabulario de `DevUserContextValue.status` ('loading'/'ready'/'error') —
 * exhaustivo por construcción: la rama `default` fuerza un error de
 * compilación (`never`) si `AuthStatus` gana un valor nuevo sin actualizar
 * este mapeo. */
function mapAuthStatus(status: AuthStatus): Status {
  switch (status) {
    case 'checking':
      return 'loading'
    case 'authenticated':
      return 'ready'
    case 'unauthenticated':
      return 'error'
    default: {
      const exhaustiveCheck: never = status
      throw new Error(`AuthStatus sin mapear: ${exhaustiveCheck}`)
    }
  }
}

/** Deriva el shape de `DevUserContextValue` a partir del usuario real
 * autenticado (`VITE_AUTH_MODE=real`) — `role`/`id` incluidos, mismo tipo
 * `CurrentUser` que ya devuelve `GET /api/v1/me` (ver
 * `app/api/schemas.py::CurrentUserResponse` en el backend), así que el
 * gating de permisos de páginas como `IntegrationsPage`/`RetentionPage`
 * (que leen `currentUser?.role`) sigue funcionando sin cambios. `devUsers`
 * y `selectUser` no tienen equivalente en modo real — nada los consume
 * fuera de `DevUserSwitcher`, que solo se monta en modo fake. */
function fromAuthContext(auth: AuthContextValue): DevUserContextValue {
  return {
    devUsers: [],
    currentUser: auth.currentUser,
    selectedUserId: auth.currentUser?.id ?? null,
    status: mapAuthStatus(auth.status),
    errorMessage: auth.errorMessage,
    selectUser: () => {
      // No-op: no existe selector de usuario de desarrollo en modo real.
    },
  }
}

/** Funciona en los dos modos de autenticación (Fase 9, hito 9.2):
 * - Modo fake (`VITE_AUTH_MODE=fake`, por defecto): dentro de
 *   `<DevUserProvider>` (ver `FakeAuthApp` en App.tsx), devuelve su valor
 *   sin cambios — comportamiento idéntico al de siempre.
 * - Modo real (`VITE_AUTH_MODE=real`): `RealAuthApp` no monta
 *   `<DevUserProvider>` (no tiene sentido elegir un usuario ficticio con
 *   sesión real), así que se deriva el mismo shape del usuario
 *   autenticado vía `useAuthOptional()` — ver `fromAuthContext` arriba.
 *   Esto evita que las páginas de `AppRoutes` (`PatientsPage`,
 *   `ClinicalSessionsPage`, etc., que llaman a `useDevUser()` sin saber en
 *   qué modo está la app) crasheen en modo real.
 *
 * Sigue lanzando si ni `<DevUserProvider>` ni `<AuthProvider>` están
 * presentes — el guardarraíl original, ahora cubriendo ambos casos. */
export function useDevUser(): DevUserContextValue {
  const devUserContext = useContext(DevUserContext)
  const authContext = useAuthOptional()
  if (devUserContext) {
    return devUserContext
  }
  if (authContext) {
    return fromAuthContext(authContext)
  }
  throw new Error(
    'useDevUser debe usarse dentro de <DevUserProvider> (modo fake) o <AuthProvider> (modo real)',
  )
}
