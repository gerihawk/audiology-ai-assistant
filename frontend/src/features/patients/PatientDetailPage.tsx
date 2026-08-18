import { useNavigate, useParams } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { useProfessionalOptions } from '../clinicalSessions/useProfessionalOptions'
import { PatientDetail } from './PatientDetail'
import { usePatient } from './usePatient'

export function PatientDetailPage() {
  const { patientId = '' } = useParams()
  const navigate = useNavigate()
  const { currentUser, selectedUserId, status } = useDevUser()
  const professionalOptions = useProfessionalOptions(currentUser)
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
    <PatientDetail
      devUserId={selectedUserId}
      role={currentUser?.role}
      currentUserId={currentUser?.id}
      professionalOptions={professionalOptions}
      patient={patientState.patient}
      onBack={() => navigate('/patients')}
      onEdit={() => navigate(`/patients/${patientId}/edit`)}
      onChanged={patientState.setPatient}
    />
  )
}
