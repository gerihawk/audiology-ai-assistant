import { formatDateTime } from '../clinicalSessions/format'
import { ClinicalRecordDocumentCard } from './ClinicalRecordDocumentCard'
import { sessionTypeLabel } from './format'
import type { ClinicalRecordSessionEntry, DevUser } from '../../shared/api/types'

interface Props {
  session: ClinicalRecordSessionEntry
  professionalOptions: DevUser[]
}

/** Una sesión dentro de la historia clínica longitudinal, en el orden
 * recibido del backend (nunca se reordena en frontend). Una sesión sin
 * documentos aprobados es un estado válido y distinto de "sin sesiones":
 * se representa explícitamente, no se oculta la sesión. */
export function ClinicalRecordSessionCard({ session, professionalOptions }: Props) {
  return (
    <li className="clinical-record-session">
      <h5>
        {formatDateTime(session.created_at)} — {sessionTypeLabel(session.session_type)}
      </h5>

      {session.documents.length === 0 ? (
        <p>Sin documentos aprobados en esta sesión.</p>
      ) : (
        session.documents.map((document) => (
          <ClinicalRecordDocumentCard
            key={document.ai_artifact_id}
            document={document}
            professionalOptions={professionalOptions}
          />
        ))
      )}
    </li>
  )
}
