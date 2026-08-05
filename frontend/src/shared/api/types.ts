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
