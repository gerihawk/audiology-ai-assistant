import type { CurrentUser, DevUser } from '../../shared/api/types'

/** Usuarios de la clínica del usuario activo que pueden ser profesional
 * responsable de una sesión (admin/audiologist — nunca viewer). */
export function filterProfessionalOptions(
  devUsers: DevUser[],
  currentUser: CurrentUser | null,
): DevUser[] {
  if (!currentUser) return []
  return devUsers.filter(
    (user) => user.clinic_id === currentUser.clinic_id && user.role !== 'viewer',
  )
}
