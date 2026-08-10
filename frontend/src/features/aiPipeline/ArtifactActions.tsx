import { useState } from 'react'
import { approveAIArtifact, rejectAIArtifact } from '../../shared/api/aiPipeline'
import type { AIArtifact, Role } from '../../shared/api/types'
import { canApprove, canReject } from './permissions'

type ActionKey = 'approve' | 'reject'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  /** Profesional responsable de la sesión clínica a la que pertenece el
   * artefacto — un AIArtifact no tiene el suyo propio. */
  professionalId: string
  artifact: AIArtifact
  /** Las acciones solo se ofrecen mientras se está viendo la versión
   * vigente: aprobar/rechazar siempre actúa sobre la versión actual del
   * artefacto, nunca sobre una versión histórica en pantalla. */
  isViewingCurrentVersion: boolean
  onChanged: (artifact: AIArtifact) => void
}

export function ArtifactActions({
  devUserId,
  role,
  currentUserId,
  professionalId,
  artifact,
  isViewingCurrentVersion,
  onChanged,
}: Props) {
  const [busyAction, setBusyAction] = useState<ActionKey | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  if (!isViewingCurrentVersion) {
    return (
      <p>
        Estás viendo una versión histórica. Selecciona la versión vigente para aprobarla o
        rechazarla.
      </p>
    )
  }

  const showApprove = canApprove(role, professionalId, currentUserId)
  const showReject = canReject(role, professionalId, currentUserId)

  async function handleApprove() {
    if (busyAction) return
    setBusyAction('approve')
    setActionError(null)
    try {
      const updated = await approveAIArtifact(devUserId, artifact.id)
      onChanged(updated)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo aprobar el artefacto.')
    } finally {
      setBusyAction(null)
    }
  }

  async function handleReject() {
    if (busyAction) return
    const reason = window.prompt('Motivo del rechazo (opcional):')
    if (reason === null) return // el usuario canceló el diálogo
    setBusyAction('reject')
    setActionError(null)
    try {
      const updated = await rejectAIArtifact(devUserId, artifact.id, reason || undefined)
      onChanged(updated)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo rechazar el artefacto.')
    } finally {
      setBusyAction(null)
    }
  }

  if (!showApprove && !showReject && !actionError) {
    return null
  }

  return (
    <div className="clinical-session-actions">
      {actionError && <p role="alert">{actionError}</p>}
      {showApprove && (
        <button type="button" disabled={busyAction !== null} onClick={handleApprove}>
          {busyAction === 'approve' ? 'Aprobando…' : 'Approve'}
        </button>
      )}
      {showReject && (
        <button type="button" disabled={busyAction !== null} onClick={handleReject}>
          {busyAction === 'reject' ? 'Rechazando…' : 'Reject'}
        </button>
      )}
    </div>
  )
}
