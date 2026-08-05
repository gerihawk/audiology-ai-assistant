import type { ClinicalSessionStatus } from '../../shared/api/types'
import { STATUS_LABELS } from './labels'

interface Props {
  status: ClinicalSessionStatus
}

export function ClinicalSessionBadge({ status }: Props) {
  return (
    <span className={`status-badge status-badge--${status.replace(/_/g, '-')}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}
