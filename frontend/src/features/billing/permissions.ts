import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::BILLING_PERMISSIONS (backend) — solo
// `admin` tiene alguna acción de facturación (ver `checkout-session`,
// `portal-session`, `status`), mismo patrón que
// `canManageInvitations`/`canManageIntegrations`/`canManageRetention`.
export function canManageBilling(role: Role | undefined): boolean {
  return role === 'admin'
}
