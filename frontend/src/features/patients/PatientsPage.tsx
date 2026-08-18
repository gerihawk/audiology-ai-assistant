import { useDevUser } from '../../shared/devUser/DevUserContext'
import { PatientList } from './PatientList'

export function PatientsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar pacientes.</p>
  }

  return (
    <section aria-label="Gestión de pacientes ficticios">
      <PatientList devUserId={selectedUserId} role={currentUser?.role} />
    </section>
  )
}
