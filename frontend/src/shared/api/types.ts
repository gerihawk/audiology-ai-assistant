export type Role = 'admin' | 'audiologist' | 'viewer'

export type Sex = 'female' | 'male' | 'other' | 'unspecified'

export interface CurrentUser {
  id: string
  clinic_id: string
  email: string
  display_name: string
  role: Role
}

export interface DevUser {
  id: string
  clinic_id: string
  display_name: string
  role: Role
}

export interface Patient {
  id: string
  clinic_id: string
  internal_code: string
  display_name: string | null
  birth_year: number | null
  sex: Sex | null
  preferred_language: string
  notes: string | null
  is_archived: boolean
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
  archived_at: string | null
  schema_version: number
}

export interface PatientListResponse {
  items: Patient[]
  total: number
  limit: number
  offset: number
}

export interface PatientCreateInput {
  internal_code: string
  display_name?: string | null
  birth_year?: number | null
  sex?: Sex | null
  notes?: string | null
}

export interface PatientUpdateInput {
  internal_code?: string
  display_name?: string | null
  birth_year?: number | null
  sex?: Sex | null
  notes?: string | null
}

export type SessionType =
  | 'initial_assessment'
  | 'follow_up'
  | 'hearing_aid_fitting'
  | 'hearing_aid_adjustment'
  | 'review'
  | 'other'

export type ClinicalSessionStatus =
  'scheduled' | 'in_progress' | 'completed' | 'review_pending' | 'reviewed' | 'cancelled'

export interface ClinicalSession {
  id: string
  clinic_id: string
  patient_id: string
  professional_id: string
  session_type: SessionType
  status: ClinicalSessionStatus
  scheduled_at: string | null
  started_at: string | null
  ended_at: string | null
  title: string | null
  administrative_notes: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
  schema_version: number
  is_archived: boolean
  archived_at: string | null
}

export interface ClinicalSessionListResponse {
  items: ClinicalSession[]
  total: number
  limit: number
  offset: number
}

export interface ClinicalSessionCreateInput {
  patient_id: string
  professional_id: string
  session_type: SessionType
  status?: 'scheduled' | 'in_progress' | 'completed'
  scheduled_at?: string | null
  title?: string | null
  administrative_notes?: string | null
}

export interface ClinicalSessionUpdateInput {
  session_type?: SessionType
  scheduled_at?: string | null
  title?: string | null
  administrative_notes?: string | null
  professional_id?: string
}

export interface ApiErrorDetail {
  loc?: (string | number)[]
  msg: string
  type: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    field?: string | null
    details?: ApiErrorDetail[]
  }
}
