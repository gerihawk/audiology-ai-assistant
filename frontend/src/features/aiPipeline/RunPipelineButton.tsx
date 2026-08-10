import { useState } from 'react'
import { runMockPipeline } from '../../shared/api/aiPipeline'
import type { Role, RunMockPipelineResponse } from '../../shared/api/types'
import { canTriggerPipeline } from './permissions'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalId: string
  clinicalSessionId: string
  onCompleted: (result: RunMockPipelineResponse) => void
}

export function RunPipelineButton({
  devUserId,
  role,
  currentUserId,
  professionalId,
  clinicalSessionId,
  onCompleted,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!canTriggerPipeline(role, professionalId, currentUserId)) {
    return null
  }

  async function handleClick() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await runMockPipeline(devUserId, clinicalSessionId)
      onCompleted(result)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'No se pudo ejecutar el pipeline de IA simulado.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={busy} onClick={handleClick}>
        {busy ? 'Ejecutando…' : 'Run Mock Pipeline'}
      </button>
    </div>
  )
}
