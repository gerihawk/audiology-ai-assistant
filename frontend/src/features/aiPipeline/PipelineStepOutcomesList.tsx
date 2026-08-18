import type { PipelineStepOutcome } from '../../shared/api/types'
import { getArtifactTypeLabel } from './labels'

interface Props {
  stepOutcomes: PipelineStepOutcome[]
}

const STEP_STATUS_LABELS: Record<string, string> = {
  completed: 'Completado',
  failed: 'Fallido',
  skipped: 'Omitido',
}

/** Detalle por paso de la última ejecución del pipeline — nunca reduce
 * `step_outcomes` a un contador agregado. Solo muestra los campos que el
 * contrato real de `PipelineStepOutcomeResponse` expone
 * (`ai_pipeline/api/schemas.py`): no hay `provider_name`/`model_name` ni
 * `skip_reason_code` a nivel de step (eso solo existe en el propio
 * `AIArtifact`, no aquí) — no se inventan. */
export function PipelineStepOutcomesList({ stepOutcomes }: Props) {
  if (stepOutcomes.length === 0) return null

  return (
    <ul className="pipeline-step-outcomes" aria-label="Detalle de la ejecución del pipeline">
      {stepOutcomes.map((outcome) => (
        <li key={outcome.artifact_type} className="pipeline-step-outcome">
          <strong>{getArtifactTypeLabel(outcome.artifact_type)}</strong>{' '}
          <span className={`status-badge status-badge--${outcome.status.replace(/_/g, '-')}`}>
            {STEP_STATUS_LABELS[outcome.status] ?? outcome.status}
          </span>
          {outcome.failure_reason && <p>Motivo del fallo: {outcome.failure_reason}</p>}
          {outcome.skipped_reason && <p>Motivo de la omisión: {outcome.skipped_reason}</p>}
        </li>
      ))}
    </ul>
  )
}
