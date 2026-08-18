import type { AIArtifactType } from '../../../shared/api/types'
import { AnamnesisContent } from './AnamnesisContent'
import { ClinicalFlagsContent } from './ClinicalFlagsContent'
import { MissingInformationContent } from './MissingInformationContent'
import { SessionNotesContent } from './SessionNotesContent'
import { SummaryContent } from './SummaryContent'
import { TranscriptContent } from './TranscriptContent'

interface Props {
  artifactType: AIArtifactType
  content: Record<string, unknown>
  confidence: number | null
  /** Solo relevante para `clinical_flags` — ver docs/clinical-safety.md
   * §7. Nunca hardcodeado: viaja tal cual desde `AIArtifact.ruleset_disclaimer`
   * (API), igual que `ai_disclaimer` en `AIDisclaimer`. */
  rulesetDisclaimer: string | null
}

/** Marca en tiempo de compilación que el `switch` de abajo sigue siendo
 * exhaustivo: si se añade un valor nuevo a `AIArtifactType` sin añadir su
 * `case`, esta línea deja de compilar. */
function assertExhaustive(value: never): never {
  return value
}

/** Traduce el `content` (JSON) de cada tipo de artefacto a una vista
 * legible — nunca se muestra JSON crudo al usuario. */
export function ArtifactContent({ artifactType, content, confidence, rulesetDisclaimer }: Props) {
  switch (artifactType) {
    case 'transcript':
      return <TranscriptContent content={content} />
    case 'summary':
      return <SummaryContent content={content} />
    case 'patient_summary':
      // Mismo contrato que `summary` ({text: string}) — ver
      // backend/app/ai_pipeline/domain/steps/patient_summary_step.py.
      // Reutiliza el componente en vez de duplicarlo solo por el nombre.
      return <SummaryContent content={content} />
    case 'clinical_flags':
      return (
        <ClinicalFlagsContent
          content={content}
          confidence={confidence}
          rulesetDisclaimer={rulesetDisclaimer}
        />
      )
    case 'missing_information':
      return <MissingInformationContent content={content} />
    case 'anamnesis':
      return <AnamnesisContent content={content} />
    case 'session_notes':
      return <SessionNotesContent content={content} />
    default:
      // Nunca "silenciosamente vacío": si en runtime llega un
      // artifact_type que esta versión del frontend no conoce todavía
      // (JSON sin validar, el tipo TS no lo impide en tiempo de
      // ejecución), se muestra un aviso explícito en vez de nada.
      assertExhaustive(artifactType)
      return (
        <p role="alert">
          Tipo de artefacto no reconocido por esta versión de la aplicación ({String(artifactType)}
          ). Actualiza la aplicación o consulta con soporte técnico.
        </p>
      )
  }
}
