import type { ClinicalSession, ClinicalSessionStatus, Role } from '../../shared/api/types'

// Refleja core/authorization.py y clinical_sessions/domain/state_machine.py
// (backend). El backend es la autoridad real: esto solo evita mostrar
// acciones que el servidor rechazaría, para una mejor experiencia de uso.
// A diferencia de `patients`, aquí un `audiologist` solo puede actuar
// sobre sus propias sesiones (professional_id === su propio id).

type SessionOwnership = Pick<ClinicalSession, 'professional_id'>
type SessionOwnershipStatusAndArchive = Pick<
  ClinicalSession,
  'professional_id' | 'status' | 'is_archived'
>

function isOwnSession(session: SessionOwnership, currentUserId: string | undefined): boolean {
  return session.professional_id === currentUserId
}

function canActOnSession(
  role: Role | undefined,
  session: SessionOwnership,
  currentUserId: string | undefined,
): boolean {
  if (role === 'admin') return true
  if (role === 'audiologist') return isOwnSession(session, currentUserId)
  return false
}

export function canCreateSession(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}

export function canUpdateMetadata(
  role: Role | undefined,
  session: SessionOwnership,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, session, currentUserId)
}

export function canChangeProfessional(role: Role | undefined): boolean {
  return role === 'admin'
}

export function canStart(
  role: Role | undefined,
  session: SessionOwnershipStatusAndArchive,
  currentUserId: string | undefined,
): boolean {
  if (session.is_archived) return false
  if (!canActOnSession(role, session, currentUserId)) return false
  return session.status === 'scheduled'
}

export function canComplete(
  role: Role | undefined,
  session: SessionOwnershipStatusAndArchive,
  currentUserId: string | undefined,
): boolean {
  if (session.is_archived) return false
  if (!canActOnSession(role, session, currentUserId)) return false
  return session.status === 'in_progress'
}

export function canSubmitReview(
  role: Role | undefined,
  session: SessionOwnershipStatusAndArchive,
  currentUserId: string | undefined,
): boolean {
  if (session.is_archived) return false
  if (!canActOnSession(role, session, currentUserId)) return false
  return session.status === 'completed'
}

export function canReview(
  role: Role | undefined,
  session: Pick<ClinicalSession, 'status'>,
): boolean {
  return role === 'admin' && session.status === 'review_pending'
}

export function canCancel(
  role: Role | undefined,
  session: SessionOwnershipStatusAndArchive,
  currentUserId: string | undefined,
): boolean {
  if (session.is_archived) return false
  if (!canActOnSession(role, session, currentUserId)) return false
  return session.status === 'scheduled' || session.status === 'in_progress'
}

export function canArchive(
  role: Role | undefined,
  session: SessionOwnershipStatusAndArchive,
  currentUserId: string | undefined,
): boolean {
  if (session.is_archived) return false
  if (!canActOnSession(role, session, currentUserId)) return false
  return (
    session.status === 'completed' ||
    session.status === 'reviewed' ||
    session.status === 'cancelled'
  )
}

export function canRestore(
  role: Role | undefined,
  session: Pick<ClinicalSession, 'is_archived'>,
): boolean {
  return role === 'admin' && session.is_archived
}

/** Campos editables vía PATCH según el estado (ver data-model.md §8). */
export function editableFieldsForStatus(
  status: ClinicalSessionStatus,
): 'all' | 'restricted' | 'none' {
  if (status === 'reviewed' || status === 'cancelled') return 'none'
  if (status === 'review_pending') return 'restricted'
  return 'all'
}
