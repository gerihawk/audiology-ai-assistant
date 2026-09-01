import { apiRequest } from './client'
import type {
  ClinicalSession,
  ClinicalSessionCreateInput,
  ClinicalSessionListResponse,
  ClinicalSessionStatus,
  ClinicalSessionUpdateInput,
  DevUser,
  SessionType,
} from './types'

export interface ListClinicalSessionsParams {
  patientId?: string
  professionalId?: string
  status?: ClinicalSessionStatus
  sessionType?: SessionType
  scheduledFrom?: string
  scheduledTo?: string
  search?: string
  includeArchived?: boolean
  limit?: number
  offset?: number
}

export function listClinicalSessions(
  devUserId: string,
  params: ListClinicalSessionsParams = {},
): Promise<ClinicalSessionListResponse> {
  const query = new URLSearchParams()
  if (params.patientId) query.set('patient_id', params.patientId)
  if (params.professionalId) query.set('professional_id', params.professionalId)
  if (params.status) query.set('status', params.status)
  if (params.sessionType) query.set('session_type', params.sessionType)
  if (params.scheduledFrom) query.set('scheduled_from', params.scheduledFrom)
  if (params.scheduledTo) query.set('scheduled_to', params.scheduledTo)
  if (params.search) query.set('search', params.search)
  if (params.includeArchived) query.set('include_archived', 'true')
  query.set('limit', String(params.limit ?? 20))
  query.set('offset', String(params.offset ?? 0))
  return apiRequest<ClinicalSessionListResponse>(`/api/v1/clinical-sessions?${query.toString()}`, {
    devUserId,
  })
}

export function getClinicalSession(devUserId: string, sessionId: string): Promise<ClinicalSession> {
  return apiRequest<ClinicalSession>(`/api/v1/clinical-sessions/${sessionId}`, { devUserId })
}

export function createClinicalSession(
  devUserId: string,
  data: ClinicalSessionCreateInput,
): Promise<ClinicalSession> {
  return apiRequest<ClinicalSession>('/api/v1/clinical-sessions', {
    method: 'POST',
    body: data,
    devUserId,
  })
}

export function updateClinicalSession(
  devUserId: string,
  sessionId: string,
  data: ClinicalSessionUpdateInput,
): Promise<ClinicalSession> {
  return apiRequest<ClinicalSession>(`/api/v1/clinical-sessions/${sessionId}`, {
    method: 'PATCH',
    body: data,
    devUserId,
  })
}

function transition(action: string) {
  return (devUserId: string, sessionId: string): Promise<ClinicalSession> =>
    apiRequest<ClinicalSession>(`/api/v1/clinical-sessions/${sessionId}/${action}`, {
      method: 'POST',
      devUserId,
    })
}

/** Equivalente real (autenticado) de `listDevUsers()` para el selector de
 * "profesional responsable": usuarios de la propia clínica con rol
 * admin/audiologist y activos — misma regla que `_validate_professional`
 * en el backend (`ClinicalSessionService`). Sin `devUserId`: solo se llama
 * en modo real (`VITE_AUTH_MODE=real`), donde `client.ts` adjunta
 * `Authorization: Bearer` automáticamente — mismo patrón que
 * `GET /api/v1/me` en `AuthContext`. */
export function listEligibleProfessionals(): Promise<DevUser[]> {
  return apiRequest<DevUser[]>('/api/v1/clinical-sessions/eligible-professionals')
}

export const startClinicalSession = transition('start')
export const completeClinicalSession = transition('complete')
export const submitReviewClinicalSession = transition('submit-review')
export const reviewClinicalSession = transition('review')
export const cancelClinicalSession = transition('cancel')
export const archiveClinicalSession = transition('archive')
export const restoreClinicalSession = transition('restore')
