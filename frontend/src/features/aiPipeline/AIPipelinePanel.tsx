import { useEffect, useState } from 'react'
import { getAIArtifact } from '../../shared/api/aiPipeline'
import type {
  AIArtifact,
  PipelineStepOutcome,
  Role,
  RunPipelineResponse,
} from '../../shared/api/types'
import { ArtifactList } from './ArtifactList'
import { ArtifactViewer } from './ArtifactViewer'
import { PipelineStepOutcomesList } from './PipelineStepOutcomesList'
import { ProposeAnamnesisUpdateButton } from './ProposeAnamnesisUpdateButton'
import { RunPipelineButton } from './RunPipelineButton'

type View = { name: 'list' } | { name: 'detail'; artifact: AIArtifact }

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  clinicalSessionId: string
  professionalId: string
  /** Id de artefacto a abrir directamente al montar (deep-link por URL). */
  initialArtifactId?: string
  /** Notifica a la página contenedora que sincronice la URL con el
   * artefacto mostrado — sin ellos, la selección de artefacto sigue
   * siendo estado local (ver auditoría de navegación). */
  onArtifactSelected?: (artifact: AIArtifact) => void
  onArtifactDeselected?: () => void
}

function summarizeRun(result: RunPipelineResponse): string {
  const total = result.step_outcomes.length
  const completed = result.step_outcomes.filter((s) => s.status === 'completed').length
  if (result.status === 'completed') {
    return `Pipeline completado: ${completed}/${total} artefactos generados.`
  }
  if (result.status === 'partially_failed') {
    return `Pipeline completado parcialmente: ${completed}/${total} artefactos generados. Revisa los que fallaron o se omitieron.`
  }
  return 'El pipeline no pudo generar ningún artefacto.'
}

export function AIPipelinePanel({
  devUserId,
  role,
  currentUserId,
  clinicalSessionId,
  professionalId,
  initialArtifactId,
  onArtifactSelected,
  onArtifactDeselected,
}: Props) {
  const [view, setView] = useState<View>({ name: 'list' })
  const [refreshToken, setRefreshToken] = useState(0)
  const [lastRunSummary, setLastRunSummary] = useState<string | null>(null)
  const [lastRunStepOutcomes, setLastRunStepOutcomes] = useState<PipelineStepOutcome[]>([])
  const [initialArtifactError, setInitialArtifactError] = useState<string | null>(null)

  useEffect(() => {
    if (!initialArtifactId) return
    let cancelled = false
    setInitialArtifactError(null)
    getAIArtifact(devUserId, initialArtifactId)
      .then((artifact) => {
        if (!cancelled) setView({ name: 'detail', artifact })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setInitialArtifactError(
            error instanceof Error ? error.message : 'No se pudo cargar el artefacto.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, initialArtifactId])

  function showList() {
    setView({ name: 'list' })
    onArtifactDeselected?.()
  }

  function showDetail(artifact: AIArtifact) {
    setView({ name: 'detail', artifact })
    onArtifactSelected?.(artifact)
  }

  function handleRunCompleted(result: RunPipelineResponse) {
    setLastRunSummary(summarizeRun(result))
    setLastRunStepOutcomes(result.step_outcomes)
    setRefreshToken((token) => token + 1)
    showList()
  }

  function handleArtifactChanged(updated: AIArtifact) {
    setView({ name: 'detail', artifact: updated })
    setRefreshToken((token) => token + 1)
  }

  function handleAnamnesisUpdateArtifact(artifact: AIArtifact) {
    setRefreshToken((token) => token + 1)
    showDetail(artifact)
  }

  return (
    <section aria-label="AI Pipeline">
      <h3>AI Pipeline</h3>

      <RunPipelineButton
        devUserId={devUserId}
        role={role}
        currentUserId={currentUserId}
        professionalId={professionalId}
        clinicalSessionId={clinicalSessionId}
        onCompleted={handleRunCompleted}
      />

      {lastRunSummary && (
        <div>
          <p role="status">{lastRunSummary}</p>
          <PipelineStepOutcomesList stepOutcomes={lastRunStepOutcomes} />
        </div>
      )}

      <section aria-label="Actualización de anamnesis">
        <h4>Anamnesis</h4>
        <ProposeAnamnesisUpdateButton
          devUserId={devUserId}
          role={role}
          currentUserId={currentUserId}
          professionalId={professionalId}
          clinicalSessionId={clinicalSessionId}
          onViewArtifact={handleAnamnesisUpdateArtifact}
        />
      </section>

      {initialArtifactError && (
        <p role="alert">Error al cargar el artefacto: {initialArtifactError}</p>
      )}

      {view.name === 'list' && (
        <ArtifactList
          devUserId={devUserId}
          clinicalSessionId={clinicalSessionId}
          refreshToken={refreshToken}
          onSelect={showDetail}
        />
      )}

      {view.name === 'detail' && (
        <ArtifactViewer
          devUserId={devUserId}
          role={role}
          currentUserId={currentUserId}
          professionalId={professionalId}
          artifact={view.artifact}
          refreshToken={refreshToken}
          onBack={showList}
          onChanged={handleArtifactChanged}
        />
      )}
    </section>
  )
}
