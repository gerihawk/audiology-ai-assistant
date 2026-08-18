import { useNavigate, useParams } from 'react-router-dom'
import type { AIArtifact } from '../../shared/api/types'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { useProfessionalOptions } from './useProfessionalOptions'
import { ClinicalSessionDetail } from './ClinicalSessionDetail'
import { useClinicalSession } from './useClinicalSession'

export function ClinicalSessionDetailPage() {
  const { sessionId = '', artifactId } = useParams()
  const navigate = useNavigate()
  const { currentUser, selectedUserId, status } = useDevUser()
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
    <ClinicalSessionDetail
      devUserId={selectedUserId}
      role={currentUser?.role}
      currentUserId={currentUser?.id}
      session={sessionState.session}
      professionalOptions={professionalOptions}
      onBack={() => navigate('/clinical-sessions')}
      onEdit={() => navigate(`/clinical-sessions/${sessionId}/edit`)}
      onChanged={sessionState.setSession}
      initialArtifactId={artifactId}
      onArtifactSelected={(artifact: AIArtifact) =>
        navigate(`/clinical-sessions/${sessionId}/ai-artifacts/${artifact.id}`)
      }
      onArtifactDeselected={() => navigate(`/clinical-sessions/${sessionId}`)}
    />
  )
}
