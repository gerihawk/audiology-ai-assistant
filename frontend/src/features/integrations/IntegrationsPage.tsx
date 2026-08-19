import { useDevUser } from '../../shared/devUser/DevUserContext'
import { IntegrationsList } from './IntegrationsList'
import { canManageIntegrations } from './permissions'

export function IntegrationsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para ver las integraciones.</p>
  }

  if (!canManageIntegrations(currentUser?.role)) {
    return <p role="alert">Solo un administrador puede ver las integraciones.</p>
  }

  return (
    <div>
      <h2>Integraciones</h2>
      <IntegrationsList devUserId={selectedUserId} role={currentUser?.role} />
    </div>
  )
}
