import { useState } from 'react'
import type { AIArtifact, Role, RunMockPipelineResponse } from '../../shared/api/types'
import { ArtifactList } from './ArtifactList'
import { ArtifactViewer } from './ArtifactViewer'
import { RunPipelineButton } from './RunPipelineButton'

type View = { name: 'list' } | { name: 'detail'; artifact: AIArtifact }

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  clinicalSessionId: string
  professionalId: string
}

function summarizeRun(result: RunMockPipelineResponse): string {
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
  const [lastRunMessage, setLastRunMessage] = useState<string | null>(null)

  function handleRunCompleted(result: RunMockPipelineResponse) {
    setLastRunMessage(summarizeRun(result))
    setRefreshToken((token) => token + 1)
    setView({ name: 'list' })
  }

  function handleArtifactChanged(updated: AIArtifact) {
    setView({ name: 'detail', artifact: updated })
    setRefreshToken((token) => token + 1)
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

      {lastRunMessage && <p role="status">{lastRunMessage}</p>}

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
