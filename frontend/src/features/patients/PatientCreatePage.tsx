import { useNavigate } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { PatientForm } from './PatientForm'

export function PatientCreatePage() {
  const navigate = useNavigate()
  const { selectedUserId, status } = useDevUser()

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar pacientes.</p>
  }

  return (
    <PatientForm
      devUserId={selectedUserId}
      mode="create"
      onDone={(patient) => navigate(`/patients/${patient.id}`)}
      onCancel={() => navigate('/patients')}
    />
  )
}
