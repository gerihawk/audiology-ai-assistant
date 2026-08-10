import type { ClinicalSession, DevUser, Role } from '../../shared/api/types'
import { AIPipelinePanel } from '../aiPipeline/AIPipelinePanel'
import { ClinicalSessionBadge } from './ClinicalSessionBadge'
import { ClinicalSessionStatusActions } from './ClinicalSessionStatusActions'
import { formatDateTime, professionalName } from './format'
import { SESSION_TYPE_LABELS } from './labels'
import { canUpdateMetadata, editableFieldsForStatus } from './permissions'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  session: ClinicalSession
  professionalOptions: DevUser[]
  onBack: () => void
  onEdit: () => void
  onChanged: (session: ClinicalSession) => void
}

export function ClinicalSessionDetail({
  devUserId,
  role,
  currentUserId,
  session,
  professionalOptions,
  onBack,
  onEdit,
  onChanged,
}: Props) {
  const showEdit =
    !session.is_archived &&
    editableFieldsForStatus(session.status) !== 'none' &&
    canUpdateMetadata(role, session, currentUserId)

  return (
    <div>
      <button type="button" onClick={onBack}>
        Volver al listado
      </button>

      <h2>{session.title || SESSION_TYPE_LABELS[session.session_type]}</h2>

      <dl>
        <dt>Estado</dt>
        <dd>
          <ClinicalSessionBadge status={session.status} />
          {session.is_archived && ' (archivada)'}
        </dd>

        <dt>Tipo de sesión</dt>
        <dd>{SESSION_TYPE_LABELS[session.session_type]}</dd>

        <dt>Profesional responsable</dt>
        <dd>{professionalName(session.professional_id, professionalOptions)}</dd>

        <dt>Programada</dt>
        <dd>{formatDateTime(session.scheduled_at)}</dd>

        <dt>Iniciada</dt>
        <dd>{formatDateTime(session.started_at)}</dd>

        <dt>Finalizada</dt>
        <dd>{formatDateTime(session.ended_at)}</dd>

        {session.reviewed_by && (
          <>
            <dt>Revisada por</dt>
            <dd>{professionalName(session.reviewed_by, professionalOptions)}</dd>

            <dt>Revisada el</dt>
            <dd>{formatDateTime(session.reviewed_at)}</dd>
          </>
        )}

        <dt>Notas administrativas</dt>
        <dd>{session.administrative_notes || '—'}</dd>
      </dl>

      {showEdit && (
        <button type="button" onClick={onEdit}>
          Editar metadatos
        </button>
      )}

      <ClinicalSessionStatusActions
        devUserId={devUserId}
        role={role}
        currentUserId={currentUserId}
        session={session}
        onChanged={onChanged}
      />

      <AIPipelinePanel
        devUserId={devUserId}
        role={role}
        currentUserId={currentUserId}
        clinicalSessionId={session.id}
        professionalId={session.professional_id}
      />
    </div>
  )
}
