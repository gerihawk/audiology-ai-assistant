import { isLowConfidence } from './format'

interface Props {
  confidence: number | null
}

/** Indicador puramente visual — nunca decide nada por sí solo. Un
 * `confidence` bajo se resalta, nunca se oculta el artefacto ni se
 * bloquea ninguna acción por su causa (ver
 * docs/ai-pipeline-architecture.md §8). */
export function ConfidenceIndicator({ confidence }: Props) {
  if (confidence === null) {
    return <span className="confidence-indicator">Confianza: no disponible</span>
  }

  const low = isLowConfidence(confidence)

  return (
    <span
      className={`confidence-indicator${low ? ' confidence-indicator--low' : ''}`}
      role="img"
      aria-label={`Confianza estimada del modelo: ${confidence} de 100${low ? ', baja — revisar con especial atención' : ''}`}
    >
      <span className="confidence-indicator__bar" aria-hidden="true">
        <span className="confidence-indicator__fill" style={{ width: `${confidence}%` }} />
      </span>
      {confidence}%{low && ' (baja)'}
    </span>
  )
}
