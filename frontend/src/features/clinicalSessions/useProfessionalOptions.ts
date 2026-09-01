import { useEffect, useState } from 'react'
import { listEligibleProfessionals } from '../../shared/api/clinicalSessions'
import { listDevUsers } from '../../shared/api/devUsers'
import type { CurrentUser, DevUser } from '../../shared/api/types'
import { useIsDevUserModeActive } from '../../shared/devUser/DevUserContext'
import { filterProfessionalOptions } from './professionalOptions'

/** Usuarios de la clínica activa que pueden ser profesional responsable de
 * una sesión clínica (admin/audiologist), listos para poblar selectores.
 *
 * Dos fuentes según qué esté realmente montado (mismo criterio que
 * `useDevUser()`, nunca releer `VITE_AUTH_MODE`): modo fake ->
 * `listDevUsers()` (sin cambios); modo real -> el endpoint real
 * `GET /clinical-sessions/eligible-professionals`, ya filtrado en el
 * backend por la misma regla — `filterProfessionalOptions` se sigue
 * aplicando en los dos casos como defensa en profundidad, no solo por
 * compatibilidad. */
export function useProfessionalOptions(currentUser: CurrentUser | null): DevUser[] {
  const isFakeMode = useIsDevUserModeActive()
  const [devUsers, setDevUsers] = useState<DevUser[]>([])

  useEffect(() => {
    let cancelled = false
    const fetchUsers = isFakeMode ? listDevUsers : listEligibleProfessionals
    fetchUsers()
      .then((users) => {
        if (!cancelled) setDevUsers(users)
      })
      .catch(() => {
        if (!cancelled) setDevUsers([])
      })
    return () => {
      cancelled = true
    }
  }, [isFakeMode])

  return filterProfessionalOptions(devUsers, currentUser)
}
