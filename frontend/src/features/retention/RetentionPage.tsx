import { useDevUser } from '../../shared/devUser/DevUserContext'
import { ExpiredAudioSection } from './ExpiredAudioSection'
import { canManageRetention } from './permissions'

export function RetentionPage() {
  const { currentUser, selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar la retención de audio.</p>
  }

  if (!canManageRetention(currentUser?.role)) {
    return <p role="alert">Solo un administrador puede gestionar la retención de audio.</p>
  }

  return (
    <div>
      <h2>Retención de audio</h2>
      <ExpiredAudioSection devUserId={selectedUserId} role={currentUser?.role} />
    </div>
  )
}
