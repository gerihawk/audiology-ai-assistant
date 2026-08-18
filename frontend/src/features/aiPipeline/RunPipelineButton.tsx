import { useState } from 'react'
import { runMockPipeline, runPipeline } from '../../shared/api/aiPipeline'
import type { Role, RunPipelineResponse } from '../../shared/api/types'
import { describeActionError } from '../../shared/apiErrorMessage'
import { canTriggerPipeline } from './permissions'

type Mode = 'mock' | 'real'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalId: string
  clinicalSessionId: string
  onCompleted: (result: RunPipelineResponse) => void
}

/** Dos entrypoints con distinta superficie de riesgo (ver
 * docs/fase-6-rfc.md, corrección de frontera mock/real) — deliberadamente
 * dos botones separados, nunca uno ambiguo: "Mock" es estructuralmente
 * incapaz de tocar un proveedor real pase lo que pase en la configuración
 * del backend; "real" respeta el routing configurado y puede gastar
 * dinero. Comparten la misma autorización (`AIPipelineAction.TRIGGER`) —
 * ver `AIPipelineService._authorize_trigger`. */
export function RunPipelineButton({
  devUserId,
  role,
  currentUserId,
  professionalId,
  clinicalSessionId,
  onCompleted,
}: Props) {
  const [busyMode, setBusyMode] = useState<Mode | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!canTriggerPipeline(role, professionalId, currentUserId)) {
    return null
  }

  async function handleRun(mode: Mode) {
    if (busyMode) return
    setBusyMode(mode)
    setError(null)
    try {
      const result =
        mode === 'mock'
          ? await runMockPipeline(devUserId, clinicalSessionId)
          : await runPipeline(devUserId, clinicalSessionId)
      onCompleted(result)
    } catch (err) {
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setBusyMode(null)
    }
  }

  return (
    <div className="run-pipeline-actions">
      {error && <p role="alert">{error}</p>}

      <div className="run-pipeline-action">
        <button type="button" disabled={busyMode !== null} onClick={() => handleRun('mock')}>
          {busyMode === 'mock' ? 'Ejecutando…' : 'Run Mock Pipeline'}
        </button>
        <p className="run-pipeline-hint">
          Simulado — nunca usa proveedores externos ni genera coste, pase lo que pase en la
          configuración del backend.
        </p>
      </div>

      <div className="run-pipeline-action">
        <button type="button" disabled={busyMode !== null} onClick={() => handleRun('real')}>
          {busyMode === 'real' ? 'Ejecutando…' : 'Run Pipeline (real)'}
        </button>
        <p className="run-pipeline-hint run-pipeline-hint--warning">
          Puede usar proveedores externos reales y generar coste, según la configuración activa del
          backend.
        </p>
      </div>
    </div>
  )
}
