import { useState } from 'react'
import {
  archiveClinicalSession,
  cancelClinicalSession,
  completeClinicalSession,
  restoreClinicalSession,
  reviewClinicalSession,
  startClinicalSession,
  submitReviewClinicalSession,
} from '../../shared/api/clinicalSessions'
import type { ClinicalSession, Role } from '../../shared/api/types'
import {
  canArchive,
  canCancel,
  canComplete,
  canReview,
  canRestore,
  canStart,
  canSubmitReview,
} from './permissions'

type ActionKey =
  'start' | 'complete' | 'submit-review' | 'review' | 'cancel' | 'archive' | 'restore'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  session: ClinicalSession
  onChanged: (session: ClinicalSession) => void
}

const ACTIONS: {
  key: ActionKey
  label: string
  run: (devUserId: string, sessionId: string) => Promise<ClinicalSession>
  confirmMessage?: string
}[] = [
  { key: 'start', label: 'Iniciar', run: startClinicalSession },
  { key: 'complete', label: 'Completar', run: completeClinicalSession },
  { key: 'submit-review', label: 'Enviar a revisión', run: submitReviewClinicalSession },
  { key: 'review', label: 'Marcar como revisada', run: reviewClinicalSession },
  {
    key: 'cancel',
    label: 'Cancelar',
    run: cancelClinicalSession,
    confirmMessage: '¿Cancelar esta sesión clínica ficticia?',
  },
  {
    key: 'archive',
    label: 'Archivar',
    run: archiveClinicalSession,
    confirmMessage: '¿Archivar esta sesión clínica ficticia? Podrás restaurarla más adelante.',
  },
  { key: 'restore', label: 'Restaurar', run: restoreClinicalSession },
]

export function ClinicalSessionStatusActions({
  devUserId,
  role,
  currentUserId,
  session,
  onChanged,
}: Props) {
  const [busyAction, setBusyAction] = useState<ActionKey | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const visibility: Record<ActionKey, boolean> = {
    start: canStart(role, session, currentUserId),
    complete: canComplete(role, session, currentUserId),
    'submit-review': canSubmitReview(role, session, currentUserId),
    review: canReview(role, session),
    cancel: canCancel(role, session, currentUserId),
    archive: canArchive(role, session, currentUserId),
    restore: canRestore(role, session),
  }

  const visibleActions = ACTIONS.filter((action) => visibility[action.key])

  async function handleRun(action: (typeof ACTIONS)[number]) {
    if (busyAction) return
    if (action.confirmMessage) {
      const confirmed = window.confirm(action.confirmMessage)
      if (!confirmed) return
    }
    setBusyAction(action.key)
    setActionError(null)
    try {
      const updated = await action.run(devUserId, session.id)
      onChanged(updated)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo completar la acción.')
    } finally {
      setBusyAction(null)
    }
  }

  if (visibleActions.length === 0 && !actionError) {
    return null
  }

  return (
    <div className="clinical-session-actions">
      {actionError && <p role="alert">{actionError}</p>}
      {visibleActions.map((action) => (
        <button
          key={action.key}
          type="button"
          disabled={busyAction !== null}
          onClick={() => handleRun(action)}
        >
          {busyAction === action.key ? 'Procesando…' : action.label}
        </button>
      ))}
    </div>
  )
}
