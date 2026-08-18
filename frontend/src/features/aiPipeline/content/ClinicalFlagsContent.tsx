import { AIDisclaimer } from '../AIDisclaimer'
import { ConfidenceIndicator } from '../ConfidenceIndicator'
import { formatCategoryLabel } from '../labels'

interface ClinicalFlagData {
  category: string
  description: string
  source_excerpt: string | null
  ruleset_name: string
}

interface ItemProps {
  flag: ClinicalFlagData
  /** Confianza del artefacto completo: en este backend no existe
   * confidence por señal individual, solo por artefacto — se muestra la
   * del artefacto en cada fila con una nota aclaratoria. */
  confidence: number | null
  /** Preparado para una futura disposición por ítem (confirmar/descartar
   * una señal individualmente) — todavía no existe endpoint de backend
   * para ello (ver informe de la Fase 4.1); estas props quedan sin usar
   * hasta entonces, deliberadamente. */
  onConfirm?: () => void
  onDiscard?: () => void
}

function ClinicalFlagItem({ flag, confidence, onConfirm, onDiscard }: ItemProps) {
  return (
    <li className="artifact-flag-item">
      <p>
        <strong>{formatCategoryLabel(flag.category)}</strong>
      </p>
      <p>{flag.description}</p>
      {flag.source_excerpt && (
        <p>
          <em>Fragmento de origen:</em> «{flag.source_excerpt}»
        </p>
      )}
      <p>
        <ConfidenceIndicator confidence={confidence} />
      </p>
      {(onConfirm || onDiscard) && (
        <div>
          {onConfirm && (
            <button type="button" onClick={onConfirm}>
              Confirmar
            </button>
          )}
          {onDiscard && (
            <button type="button" onClick={onDiscard}>
              Descartar
            </button>
          )}
        </div>
      )}
    </li>
  )
}

interface Props {
  content: Record<string, unknown>
  confidence: number | null
  /** docs/clinical-safety.md §7 — obligatorio junto a las señales de
   * alerta, siempre que la API lo envíe (nunca hardcodeado aquí). */
  rulesetDisclaimer: string | null
}

export function ClinicalFlagsContent({ content, confidence, rulesetDisclaimer }: Props) {
  const flags = Array.isArray(content.flags) ? (content.flags as ClinicalFlagData[]) : []

  return (
    <div className="artifact-clinical-flags">
      {rulesetDisclaimer && <AIDisclaimer text={rulesetDisclaimer} />}

      {flags.length === 0 ? (
        <p>No se han detectado señales de alerta.</p>
      ) : (
        <ul className="artifact-flags-list">
          {flags.map((flag) => (
            // MockClinicalFlagsGenerator nunca repite categoría dentro de
            // una misma generación, así que category es una clave estable.
            <ClinicalFlagItem key={flag.category} flag={flag} confidence={confidence} />
          ))}
        </ul>
      )}
    </div>
  )
}
