import {
  ANAMNESIS_FIELD_LABELS,
  ANAMNESIS_FIELD_STATUS_LABELS,
  type AnamnesisFieldStatus,
} from '../labels'

interface AnamnesisFieldData {
  value: string
  status: AnamnesisFieldStatus
  source_excerpt: string | null
}

interface Props {
  content: Record<string, unknown>
}

/** Transforma el JSON de la anamnesis en una estructura legible (nunca se
 * muestra el JSON crudo) — un bloque por campo, con su etiqueta en
 * español, el valor, el estado (informado/negado explícitamente/no
 * preguntado/no determinado) y, cuando existe, el fragmento de origen que
 * lo respalda (mismo patrón que `SessionNotesContent`/`ClinicalFlagsContent`
 * — el backend exige `source_excerpt` no vacío para
 * informado/negado_explicitamente y `null` para no_preguntado/no_determinado,
 * ver `ai_pipeline/domain/schemas.py::_check_anamnesis_evidence_consistency`;
 * este componente solo refleja esa invariante, nunca la reformula). */
export function AnamnesisContent({ content }: Props) {
  const fieldNames = Object.keys(ANAMNESIS_FIELD_LABELS).filter((name) => name in content)

  if (fieldNames.length === 0) {
    return <p>Sin contenido.</p>
  }

  return (
    <div className="artifact-anamnesis-fields">
      {fieldNames.map((fieldName) => {
        const field = content[fieldName] as AnamnesisFieldData
        return (
          <div key={fieldName} className="artifact-anamnesis-field">
            <p>
              <strong>{ANAMNESIS_FIELD_LABELS[fieldName]}</strong>{' '}
              <span className="status-badge">{ANAMNESIS_FIELD_STATUS_LABELS[field.status]}</span>
            </p>
            {field.value && <p>{field.value}</p>}
            {field.source_excerpt && (
              <p>
                <em>Fragmento de origen:</em> «{field.source_excerpt}»
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
