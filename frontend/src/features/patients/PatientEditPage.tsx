import { useNavigate, useParams } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { PatientForm } from './PatientForm'
import { usePatient } from './usePatient'

export function PatientEditPage() {
  const { patientId = '' } = useParams()
  const navigate = useNavigate()
  const { selectedUserId, status } = useDevUser()
  const patientState = usePatient(selectedUserId ?? '', patientId)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar pacientes.</p>
  }

  if (patientState.status === 'loading') {
    return <p role="status">Cargando paciente…</p>
  }

  if (patientState.status === 'error') {
    return <p role="alert">Error al cargar el paciente: {patientState.message}</p>
  }

  return (
    <PatientForm
      devUserId={selectedUserId}
      mode="edit"
      patient={patientState.patient}
      onDone={() => navigate(`/patients/${patientId}`)}
      onCancel={() => navigate(`/patients/${patientId}`)}
    />
  )
}
