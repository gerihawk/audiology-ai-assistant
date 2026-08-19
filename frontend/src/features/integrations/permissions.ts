import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::INTEGRATION_CONFIG_PERMISSIONS (backend) —
// solo `admin` tiene alguna acción, ni siquiera `audiologist` puede leer
// (mismo patrón que `canManageRetention`).
export function canManageIntegrations(role: Role | undefined): boolean {
  return role === 'admin'
}
