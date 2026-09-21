import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::ANALYTICS_PERMISSIONS (backend) — `admin`
// y `audiologist` tienen acceso al panel (con vistas distintas, ver
// `AnalyticsPanel`), `viewer` no tiene ninguna acción — mismo patrón que
// `canManageBilling`/`canManageInvitations`.
export function canViewAnalytics(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}
