import {
  ANAMNESIS_FIELD_LABELS,
  ANAMNESIS_FIELD_STATUS_LABELS,
  type AnamnesisFieldStatus,
} from '../labels'

interface AnamnesisFieldData {
  value: string
  status: AnamnesisFieldStatus
}

interface Props {
  content: Record<string, unknown>
}

/** Transforma el JSON de la anamnesis en una estructura legible (nunca se
 * muestra el JSON crudo) — un bloque por campo, con su etiqueta en
 * español, el valor y el estado (informado/negado explícitamente/no
 * preguntado/no determinado). */
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
          </div>
        )
      })}
    </div>
  )
}
