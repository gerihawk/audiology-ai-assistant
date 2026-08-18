import { useNavigate, useParams } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { ClinicalSessionForm } from './ClinicalSessionForm'
import { useClinicalSession } from './useClinicalSession'
import { usePatientOptions } from './usePatientOptions'
import { useProfessionalOptions } from './useProfessionalOptions'

export function ClinicalSessionEditPage() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const { currentUser, selectedUserId, status } = useDevUser()
  const { patients } = usePatientOptions(selectedUserId ?? '')
  const professionalOptions = useProfessionalOptions(currentUser)
  const sessionState = useClinicalSession(selectedUserId ?? '', sessionId)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar sesiones clínicas.</p>
  }

  if (sessionState.status === 'loading') {
    return <p role="status">Cargando sesión clínica…</p>
  }

  if (sessionState.status === 'error') {
    return <p role="alert">Error al cargar la sesión clínica: {sessionState.message}</p>
  }

  return (
    <ClinicalSessionForm
      devUserId={selectedUserId}
      mode="edit"
      session={sessionState.session}
      currentUserId={currentUser?.id}
      role={currentUser?.role}
      patientOptions={patients}
      professionalOptions={professionalOptions}
      onDone={() => navigate(`/clinical-sessions/${sessionId}`)}
      onCancel={() => navigate(`/clinical-sessions/${sessionId}`)}
    />
  )
}
