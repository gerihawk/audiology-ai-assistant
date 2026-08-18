import { ArtifactContent } from '../aiPipeline/content/ArtifactContent'
import { getArtifactTypeLabel } from '../aiPipeline/labels'
import { formatDateTime, professionalName } from '../clinicalSessions/format'
import type { ClinicalRecordDocument, DevUser } from '../../shared/api/types'

interface Props {
  document: ClinicalRecordDocument
  professionalOptions: DevUser[]
}

/** Un documento de la historia clínica longitudinal. Reutiliza
 * `ArtifactContent` directamente con los campos del DTO longitudinal —
 * nunca fabrica un `AIArtifact` falso: `confidence` no existe en este
 * contrato (se pasa `null`, que `ConfidenceIndicator` ya representa como
 * "no disponible"), y `ruleset_disclaimer` viaja tal cual desde el
 * documento, igual que en `ArtifactViewer`. */
export function ClinicalRecordDocumentCard({ document, professionalOptions }: Props) {
  return (
    <div className="clinical-record-document">
      <p>
        <strong>{getArtifactTypeLabel(document.artifact_type)}</strong>{' '}
        <span>Versión {document.version_number}</span>
        {document.artifact_type === 'anamnesis' && (
          <span
            className={`anamnesis-baseline-badge anamnesis-baseline-badge--${
              document.is_current_baseline ? 'current' : 'historical'
            }`}
          >
            {document.is_current_baseline ? 'Anamnesis vigente' : 'Anamnesis histórica'}
          </span>
        )}
      </p>
      <p>
        Aprobado por {professionalName(document.approved_by, professionalOptions)} el{' '}
        {formatDateTime(document.approved_at)}
      </p>

      <ArtifactContent
        artifactType={document.artifact_type}
        content={document.content}
        confidence={null}
        rulesetDisclaimer={document.ruleset_disclaimer}
      />
    </div>
  )
}
