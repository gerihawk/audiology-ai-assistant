import type { AIArtifact } from '../../shared/api/types'
import { ArtifactStatusBadge } from './ArtifactStatusBadge'
import { ConfidenceIndicator } from './ConfidenceIndicator'
import { ARTIFACT_TYPE_LABELS } from './labels'

interface Props {
  artifact: AIArtifact
  onSelect: (artifact: AIArtifact) => void
}

export function ArtifactCard({ artifact, onSelect }: Props) {
  return (
    <li className="artifact-card">
      <span>
        <strong>{ARTIFACT_TYPE_LABELS[artifact.artifact_type]}</strong>{' '}
        <ArtifactStatusBadge status={artifact.status} />
      </span>
      <ConfidenceIndicator confidence={artifact.confidence} />
      <button type="button" onClick={() => onSelect(artifact)}>
        Ver detalle
      </button>
    </li>
  )
}
