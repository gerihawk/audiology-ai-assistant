import type { ClinicalSessionStatus, SessionType } from '../../shared/api/types'

export const SESSION_TYPE_LABELS: Record<SessionType, string> = {
  initial_assessment: 'Valoración inicial',
  follow_up: 'Seguimiento',
  hearing_aid_fitting: 'Adaptación de audífonos',
  hearing_aid_adjustment: 'Ajuste de audífonos',
  review: 'Revisión',
  other: 'Otro',
}

export const SESSION_TYPES = Object.keys(SESSION_TYPE_LABELS) as SessionType[]

export const STATUS_LABELS: Record<ClinicalSessionStatus, string> = {
  scheduled: 'Programada',
  in_progress: 'En curso',
  completed: 'Completada',
  review_pending: 'Pendiente de revisión',
  reviewed: 'Revisada',
  cancelled: 'Cancelada',
}

export const STATUSES = Object.keys(STATUS_LABELS) as ClinicalSessionStatus[]
