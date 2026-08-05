import { apiRequest } from './client'
import type { Patient, PatientCreateInput, PatientListResponse, PatientUpdateInput } from './types'

export interface ListPatientsParams {
  search?: string
  includeArchived?: boolean
  limit?: number
  offset?: number
}

export function listPatients(
  devUserId: string,
  params: ListPatientsParams = {},
): Promise<PatientListResponse> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.includeArchived) query.set('include_archived', 'true')
  query.set('limit', String(params.limit ?? 20))
  query.set('offset', String(params.offset ?? 0))
  return apiRequest<PatientListResponse>(`/api/v1/patients?${query.toString()}`, { devUserId })
}

export function getPatient(devUserId: string, patientId: string): Promise<Patient> {
  return apiRequest<Patient>(`/api/v1/patients/${patientId}`, { devUserId })
}

export function createPatient(devUserId: string, data: PatientCreateInput): Promise<Patient> {
  return apiRequest<Patient>('/api/v1/patients', { method: 'POST', body: data, devUserId })
}

export function updatePatient(
  devUserId: string,
  patientId: string,
  data: PatientUpdateInput,
): Promise<Patient> {
  return apiRequest<Patient>(`/api/v1/patients/${patientId}`, {
    method: 'PATCH',
    body: data,
    devUserId,
  })
}

export function archivePatient(devUserId: string, patientId: string): Promise<Patient> {
  return apiRequest<Patient>(`/api/v1/patients/${patientId}/archive`, {
    method: 'POST',
    devUserId,
  })
}

export function restorePatient(devUserId: string, patientId: string): Promise<Patient> {
  return apiRequest<Patient>(`/api/v1/patients/${patientId}/restore`, {
    method: 'POST',
    devUserId,
  })
}
