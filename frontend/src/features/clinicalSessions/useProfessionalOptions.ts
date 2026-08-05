import { useEffect, useState } from 'react'
import { listDevUsers } from '../../shared/api/devUsers'
import type { CurrentUser, DevUser } from '../../shared/api/types'
import { filterProfessionalOptions } from './professionalOptions'

/** Usuarios de la clínica activa que pueden ser profesional responsable de
 * una sesión clínica (admin/audiologist), listos para poblar selectores. */
export function useProfessionalOptions(currentUser: CurrentUser | null): DevUser[] {
  const [devUsers, setDevUsers] = useState<DevUser[]>([])

  useEffect(() => {
    let cancelled = false
    listDevUsers()
      .then((users) => {
        if (!cancelled) setDevUsers(users)
      })
      .catch(() => {
        if (!cancelled) setDevUsers([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  return filterProfessionalOptions(devUsers, currentUser)
}
