import { apiRequest } from './client'
import type { Consent, ConsentCreateInput, ConsentListResponse } from './types'

export function listConsents(devUserId: string, patientId: string): Promise<ConsentListResponse> {
  return apiRequest<ConsentListResponse>(`/api/v1/patients/${patientId}/consents`, { devUserId })
}

export function createConsent(
  devUserId: string,
  patientId: string,
  data: ConsentCreateInput,
): Promise<Consent> {
  return apiRequest<Consent>(`/api/v1/patients/${patientId}/consents`, {
    method: 'POST',
    body: data,
    devUserId,
  })
}
