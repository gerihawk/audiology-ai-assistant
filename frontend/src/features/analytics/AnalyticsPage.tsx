import { useDevUser } from '../../shared/devUser/DevUserContext'
import { AnalyticsPanel } from './AnalyticsPanel'
import { canViewAnalytics } from './permissions'

/** Gate de acceso al apartado "Analítica" (Fase 15) — mismo patrón que
 * `BillingPage`/`IntegrationsPage`: solo resuelve `useDevUser()` y delega
 * toda la lógica/UI a `AnalyticsPanel`, que recibe `devUserId`/`role` por
 * props y es lo que se testea directamente. */
export function AnalyticsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para ver la analítica.</p>
  }

  if (!canViewAnalytics(currentUser?.role)) {
    return <p role="alert">No tienes acceso al panel de analítica.</p>
  }

  return <AnalyticsPanel devUserId={selectedUserId} role={currentUser?.role} />
}
