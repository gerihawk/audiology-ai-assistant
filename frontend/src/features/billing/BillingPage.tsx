import { useDevUser } from '../../shared/devUser/DevUserContext'
import { BillingPanel } from './BillingPanel'
import { canManageBilling } from './permissions'

/** Gate de acceso al apartado "Facturación" (Fase 13, hito 13.3) — mismo
 * patrón que `IntegrationsPage`/`InvitationsPage`: solo resuelve
 * `useDevUser()` y delega toda la lógica/UI a `BillingPanel`, que recibe
 * `devUserId`/`role` por props y es lo que se testea directamente. */
export function BillingPage() {
  const { currentUser, selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para ver la facturación.</p>
  }

  if (!canManageBilling(currentUser?.role)) {
    return <p role="alert">Solo un administrador puede gestionar la facturación.</p>
  }

  return <BillingPanel devUserId={selectedUserId} role={currentUser?.role} />
}
