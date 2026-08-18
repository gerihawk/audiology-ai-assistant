import { useNavigate } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { ClinicalSessionForm } from './ClinicalSessionForm'
import { usePatientOptions } from './usePatientOptions'
import { useProfessionalOptions } from './useProfessionalOptions'

export function ClinicalSessionCreatePage() {
  const navigate = useNavigate()
  const { currentUser, selectedUserId, status } = useDevUser()
  const { patients } = usePatientOptions(selectedUserId ?? '')
  const professionalOptions = useProfessionalOptions(currentUser)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar sesiones clínicas.</p>
  }

  return (
    <ClinicalSessionForm
      devUserId={selectedUserId}
      mode="create"
      currentUserId={currentUser?.id}
      role={currentUser?.role}
      patientOptions={patients}
      professionalOptions={professionalOptions}
      onDone={(session) => navigate(`/clinical-sessions/${session.id}`)}
      onCancel={() => navigate('/clinical-sessions')}
    />
  )
}
