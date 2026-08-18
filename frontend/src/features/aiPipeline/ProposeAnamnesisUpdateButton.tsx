import { useState } from 'react'
import { getAIArtifact, proposeAnamnesisUpdate } from '../../shared/api/aiPipeline'
import type { AIArtifact, AnamnesisUpdateProposalResponse, Role } from '../../shared/api/types'
import { describeActionError } from './apiErrorMessage'
import { ANAMNESIS_FIELD_LABELS } from './labels'
import { canProposeAnamnesisUpdate } from './permissions'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalId: string
  clinicalSessionId: string
  onViewArtifact: (artifact: AIArtifact) => void
}

/** Acción EXPLÍCITA y separada de run-pipeline/run-mock-pipeline — nunca se
 * dispara automáticamente (ver `AIPipelineService.propose_anamnesis_update`,
 * RFC técnico de 6.5 §0/§3). `created=false` ("no changes proposed") es un
 * resultado válido, nunca un error. */
export function ProposeAnamnesisUpdateButton({
  devUserId,
  role,
  currentUserId,
  professionalId,
  clinicalSessionId,
  onViewArtifact,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AnamnesisUpdateProposalResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingArtifact, setLoadingArtifact] = useState(false)

  if (!canProposeAnamnesisUpdate(role, professionalId, currentUserId)) {
    return null
  }

  async function handleClick() {
    if (busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const response = await proposeAnamnesisUpdate(devUserId, clinicalSessionId)
      setResult(response)
    } catch (err) {
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleViewArtifact(artifactId: string) {
    setLoadingArtifact(true)
    try {
      const artifact = await getAIArtifact(devUserId, artifactId)
      onViewArtifact(artifact)
    } catch (err) {
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setLoadingArtifact(false)
    }
  }

  return (
    <div className="propose-anamnesis-update">
      <button type="button" disabled={busy} onClick={handleClick}>
        {busy ? 'Proponiendo…' : 'Proponer actualización de anamnesis'}
      </button>

      {error && <p role="alert">{error}</p>}

      {result && (
        <div role="status">
          {result.created ? (
            <>
              <p>Se ha creado una propuesta de actualización de anamnesis.</p>
              {result.changed_fields.length > 0 && (
                <ul>
                  {result.changed_fields.map((fieldName) => (
                    <li key={fieldName}>{ANAMNESIS_FIELD_LABELS[fieldName] ?? fieldName}</li>
                  ))}
                </ul>
              )}
              {result.artifact_id && (
                <button
                  type="button"
                  disabled={loadingArtifact}
                  onClick={() => handleViewArtifact(result.artifact_id as string)}
                >
                  {loadingArtifact ? 'Cargando…' : 'Ver anamnesis propuesta'}
                </button>
              )}
            </>
          ) : (
            <p>No se han propuesto cambios.</p>
          )}
          <p className="ai-disclaimer" role="note">
            {result.ai_disclaimer}
          </p>
        </div>
      )}
    </div>
  )
}
