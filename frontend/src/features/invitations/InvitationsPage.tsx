import { useState } from 'react'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { InvitationForm } from './InvitationForm'
import { InvitationsList } from './InvitationsList'
import { canManageInvitations } from './permissions'

/** Fase 12, hito 12.3: página de administración de invitaciones — un
 * admin invita a otro usuario de su propia clínica (`current_user.clinic_id`,
 * ver `authorize_invitation_action`) y gestiona las pendientes. Mismo
 * patrón de gating que `IntegrationsPage`. */
export function InvitationsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()
  const [reloadSignal, setReloadSignal] = useState(0)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para ver las invitaciones.</p>
  }

  if (!currentUser || !canManageInvitations(currentUser.role)) {
    return <p role="alert">Solo un administrador puede gestionar invitaciones.</p>
  }

  return (
    <div>
      <h2>Invitaciones</h2>
      <InvitationForm
        clinicId={currentUser.clinic_id}
        devUserId={selectedUserId}
        onInvited={() => setReloadSignal((value) => value + 1)}
      />
      <InvitationsList
        clinicId={currentUser.clinic_id}
        devUserId={selectedUserId}
        reloadSignal={reloadSignal}
      />
    </div>
  )
}
