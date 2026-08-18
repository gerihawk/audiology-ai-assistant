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

export type AIArtifactType =
  | 'transcript'
  | 'summary'
  | 'patient_summary'
  | 'clinical_flags'
  | 'missing_information'
  | 'anamnesis'
  | 'session_notes'

export type AIArtifactStatus = 'review_pending' | 'approved' | 'rejected'

export type AIArtifactVersionSource = 'ai_generated' | 'human_edited'

export type AIPipelineRunStatus =
  'queued' | 'processing' | 'completed' | 'failed' | 'partially_failed'

export interface AIArtifact {
  id: string
  clinical_session_id: string
  artifact_type: AIArtifactType
  status: AIArtifactStatus
  version_number: number | null
  content: Record<string, unknown> | null
  confidence: number | null
  provider_name: string | null
  model_name: string | null
  schema_version: number
  approved_by: string | null
  approved_at: string | null
  rejected_by: string | null
  rejected_at: string | null
  rejection_reason: string | null
  created_at: string
  updated_at: string
  ai_disclaimer: string
  /** Solo presente (no null) cuando `artifact_type === 'clinical_flags'` —
   * ver docs/clinical-safety.md §7. `null` para el resto de tipos. */
  ruleset_disclaimer: string | null
}

export interface AIArtifactListResponse {
  items: AIArtifact[]
}

export interface AIArtifactVersion {
  id: string
  version_number: number
  content: Record<string, unknown>
  confidence: number | null
  source: AIArtifactVersionSource
  provider_name: string | null
  model_name: string | null
  is_current: boolean
  created_at: string
}

export interface AIArtifactVersionListResponse {
  items: AIArtifactVersion[]
}

export interface PipelineStepOutcome {
  artifact_type: AIArtifactType
  status: string
  failure_reason: string | null
  skipped_reason: string | null
  latency_ms: number | null
  execution_time_ms: number | null
  input_token_count: number | null
  output_token_count: number | null
  estimated_cost_usd: string | null
}

/** Forma de respuesta compartida por `run-pipeline` (real) y
 * `run-mock-pipeline` — el backend documenta que es idéntica en ambos
 * casos (ver `RunPipelineResponse` en `ai_pipeline/api/schemas.py`); la
 * diferencia está en qué generators se ejecutan, nunca en la forma de la
 * respuesta. */
export interface RunPipelineResponse {
  pipeline_run_id: string
  status: AIPipelineRunStatus
  started_at: string
  completed_at: string | null
  artifacts: AIArtifact[]
  step_outcomes: PipelineStepOutcome[]
}

/** Entrada de `PATCH /ai-artifacts/{id}/content` — ver `ArtifactEditRequest`
 * (`ai_pipeline/api/schemas.py`). */
export interface ArtifactEditInput {
  content: Record<string, unknown>
  change_note?: string | null
}

/** Respuesta de `POST /clinical-sessions/{id}/propose-anamnesis-update` —
 * ver `AnamnesisUpdateProposalResponse` (`ai_pipeline/api/schemas.py`).
 * `created=false` es un resultado válido ("no changes proposed"), nunca un
 * error: en ese caso `artifact_id`/`version_number`/`status` son `null` y
 * `changed_fields` está vacío. */
export interface AnamnesisUpdateProposalResponse {
  created: boolean
  artifact_id: string | null
  version_number: number | null
  status: AIArtifactStatus | null
  changed_fields: string[]
  ai_disclaimer: string
}

/** `Literal["pdf", "text"]` en el backend (`export/service.py`,
 * `clinical_record/service.py`) — mismo valor para exportación individual
 * y longitudinal. */
export type ExportFormat = 'pdf' | 'text'

/** `ClinicalRecordDocumentResponse` (`clinical_record/api/schemas.py`).
 * Deliberadamente sin `confidence`, `provider_name`, `model_name`,
 * `source_map` ni coste — el contrato longitudinal no los expone (ver
 * `clinical_record/domain/entities.py::strip_source_excerpt`, que además
 * elimina recursivamente `source_excerpt` de `content` para todos los
 * tipos). No es un `AIArtifact`: no se debe fabricar uno falso a partir de
 * esto. */
export interface ClinicalRecordDocument {
  ai_artifact_id: string
  artifact_type: AIArtifactType
  version_number: number
  approved_by: string
  approved_at: string
  content: Record<string, unknown>
  /** Solo tiene sentido para `artifact_type === 'anamnesis'` — el backend
   * lo calcula una única vez sobre el paciente completo
   * (`_apply_known_anamnesis_baseline`), nunca se recalcula aquí. */
  is_current_baseline: boolean
  ruleset_disclaimer: string | null
}

export interface ClinicalRecordSessionEntry {
  clinical_session_id: string
  session_type: string | null
  created_at: string
  documents: ClinicalRecordDocument[]
}

export interface ClinicalRecordPage {
  patient_id: string
  patient_internal_code: string
  patient_display_name: string | null
  sessions: ClinicalRecordSessionEntry[]
  total: number
  limit: number
  offset: number
  ai_disclaimer: string
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
