import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
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

export function useDevUser(): DevUserContextValue {
  const context = useContext(DevUserContext)
  if (!context) {
    throw new Error('useDevUser debe usarse dentro de <DevUserProvider>')
  }
  return context
}
