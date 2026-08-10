import { ArtifactStatusBadge } from './ArtifactStatusBadge'
import { ConfidenceIndicator } from './ConfidenceIndicator'
import { formatDateTime } from './format'

interface Props {
  status: 'review_pending' | 'approved' | 'rejected'
  versionNumber: number
  isCurrentVersion: boolean
  confidence: number | null
  providerName: string | null
  modelName: string | null
  createdAt: string
  approvedAt: string | null
  rejectedAt: string | null
  rejectionReason: string | null
}

export function ArtifactMetadata({
  status,
  versionNumber,
  isCurrentVersion,
  confidence,
  providerName,
  modelName,
  createdAt,
  approvedAt,
  rejectedAt,
  rejectionReason,
}: Props) {
  return (
    <dl>
      <dt>Estado</dt>
      <dd>
        <ArtifactStatusBadge status={status} />
      </dd>

      <dt>Versión</dt>
      <dd>
        {versionNumber}
        {isCurrentVersion ? ' (vigente)' : ' (histórica)'}
      </dd>

      <dt>Confianza</dt>
      <dd>
        <ConfidenceIndicator confidence={confidence} />
      </dd>

      <dt>Proveedor</dt>
      <dd>{providerName ?? '—'}</dd>

      <dt>Modelo</dt>
      <dd>{modelName ?? '—'}</dd>

      <dt>Generado el</dt>
      <dd>{formatDateTime(createdAt)}</dd>

      {approvedAt && (
        <>
          <dt>Aprobado el</dt>
          <dd>{formatDateTime(approvedAt)}</dd>
        </>
      )}

      {rejectedAt && (
        <>
          <dt>Rechazado el</dt>
          <dd>{formatDateTime(rejectedAt)}</dd>
          <dt>Motivo del rechazo</dt>
          <dd>{rejectionReason || '—'}</dd>
        </>
      )}
    </dl>
  )
}
