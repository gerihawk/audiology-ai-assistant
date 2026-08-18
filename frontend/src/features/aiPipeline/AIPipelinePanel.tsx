import { useState } from 'react'
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
}: Props) {
  const [view, setView] = useState<View>({ name: 'list' })
  const [refreshToken, setRefreshToken] = useState(0)
  const [lastRunSummary, setLastRunSummary] = useState<string | null>(null)
  const [lastRunStepOutcomes, setLastRunStepOutcomes] = useState<PipelineStepOutcome[]>([])

  function handleRunCompleted(result: RunPipelineResponse) {
    setLastRunSummary(summarizeRun(result))
    setLastRunStepOutcomes(result.step_outcomes)
    setRefreshToken((token) => token + 1)
    setView({ name: 'list' })
  }

  function handleArtifactChanged(updated: AIArtifact) {
    setView({ name: 'detail', artifact: updated })
    setRefreshToken((token) => token + 1)
  }

  function handleAnamnesisUpdateArtifact(artifact: AIArtifact) {
    setRefreshToken((token) => token + 1)
    setView({ name: 'detail', artifact })
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

      {view.name === 'list' && (
        <ArtifactList
          devUserId={devUserId}
          clinicalSessionId={clinicalSessionId}
          refreshToken={refreshToken}
          onSelect={(artifact) => setView({ name: 'detail', artifact })}
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
          onBack={() => setView({ name: 'list' })}
          onChanged={handleArtifactChanged}
        />
      )}
    </section>
  )
}
