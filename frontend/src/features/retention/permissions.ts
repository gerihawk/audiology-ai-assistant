import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::RETENTION_PERMISSIONS (backend) — solo
// `admin` tiene alguna acción sobre retención; ni siquiera `audiologist`
// puede leer o purgar (a diferencia del patrón de `consents`).
export function canManageRetention(role: Role | undefined): boolean {
  return role === 'admin'
}
