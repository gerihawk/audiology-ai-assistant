import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::INVITATION_PERMISSIONS (backend) — solo
// `admin` tiene alguna acción (crear, leer, revocar), ni siquiera
// `audiologist` puede ver invitaciones pendientes (mismo patrón que
// `canManageIntegrations`/`canManageRetention`).
export function canManageInvitations(role: Role | undefined): boolean {
  return role === 'admin'
}
