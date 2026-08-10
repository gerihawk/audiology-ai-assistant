import type { AIArtifactStatus } from '../../shared/api/types'
import { ARTIFACT_STATUS_LABELS } from './labels'

interface Props {
  status: AIArtifactStatus
}

export function ArtifactStatusBadge({ status }: Props) {
  return (
    <span className={`status-badge status-badge--${status.replace(/_/g, '-')}`}>
      {ARTIFACT_STATUS_LABELS[status]}
    </span>
  )
}
