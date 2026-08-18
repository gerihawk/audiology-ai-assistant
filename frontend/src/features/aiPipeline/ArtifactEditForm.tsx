import { useState } from 'react'
import type { FormEvent } from 'react'
import { editAIArtifactContent } from '../../shared/api/aiPipeline'
import type { AIArtifact, AIArtifactType, AIArtifactVersion, Role } from '../../shared/api/types'
import { describeActionError } from '../../shared/apiErrorMessage'
import { canEdit } from './permissions'

/** Alcance de este bloque (ver informe de auditoría): solo los tipos con
 * contenido `{text: string}` — editables con un único campo de texto plano,
 * sin exponer JSON. El resto de tipos (`transcript`, `clinical_flags`,
 * `missing_information`, `anamnesis`, `session_notes`) tienen shapes
 * estructurados con invariantes propios (listas, enums, campos ligados a
 * `source_excerpt`) que requieren su propio formulario dedicado — no un
 * editor genérico. Ampliar esta lista sin diseñar ese formulario
 * reproduciría el problema que se quiere evitar. */
const EDITABLE_ARTIFACT_TYPES: AIArtifactType[] = ['summary', 'patient_summary']

function isArtifactTypeEditable(artifactType: AIArtifactType): boolean {
  return EDITABLE_ARTIFACT_TYPES.includes(artifactType)
}

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalId: string
  artifact: AIArtifact
  currentVersion: AIArtifactVersion
  /** Igual que en `ArtifactActions`: editar siempre actúa sobre la versión
   * vigente, nunca sobre una versión histórica en pantalla. */
  isViewingCurrentVersion: boolean
  onChanged: (artifact: AIArtifact) => void
}

export function ArtifactEditForm({
  devUserId,
  role,
  currentUserId,
  professionalId,
  artifact,
  currentVersion,
  isViewingCurrentVersion,
  onChanged,
}: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [text, setText] = useState('')
  const [changeNote, setChangeNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isViewingCurrentVersion) return null
  if (!isArtifactTypeEditable(artifact.artifact_type)) return null
  if (!canEdit(role, professionalId, currentUserId)) return null

  function startEditing() {
    const currentText =
      typeof currentVersion.content.text === 'string' ? currentVersion.content.text : ''
    setText(currentText)
    setChangeNote('')
    setError(null)
    setIsEditing(true)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      // Nunca se muta `artifact`/`currentVersion` localmente: el estado
      // que pasa a `onChanged` es siempre la respuesta real del PATCH.
      const updated = await editAIArtifactContent(devUserId, artifact.id, {
        content: { text },
        change_note: changeNote || null,
      })
      onChanged(updated)
      setIsEditing(false)
    } catch (err) {
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (!isEditing) {
    return (
      <button type="button" onClick={startEditing}>
        Editar contenido
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Editar contenido del artefacto">
      {error && <p role="alert">{error}</p>}
      <p>
        Guardar esta edición creará una nueva versión y devolverá el artefacto a{' '}
        <strong>pendiente de revisión</strong> — nunca se aprueba automáticamente.
      </p>

      <label htmlFor="artifact-edit-text">Contenido</label>
      <textarea
        id="artifact-edit-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        required
        rows={8}
      />

      <label htmlFor="artifact-edit-change-note">Nota de cambio (opcional)</label>
      <textarea
        id="artifact-edit-change-note"
        value={changeNote}
        onChange={(event) => setChangeNote(event.target.value)}
        maxLength={2000}
      />

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Guardando…' : 'Guardar edición'}
        </button>
        <button type="button" onClick={() => setIsEditing(false)} disabled={submitting}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
