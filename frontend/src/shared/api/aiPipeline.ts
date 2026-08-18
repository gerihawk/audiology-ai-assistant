import { apiRequest } from './client'
import type {
  AIArtifact,
  AIArtifactListResponse,
  AIArtifactVersionListResponse,
  AnamnesisUpdateProposalResponse,
  ArtifactEditInput,
  RunPipelineResponse,
} from './types'

/** Mock — cero LLM externo, determinista, nunca gasta dinero pase lo que
 * pase en la configuración del backend (ver `AIPipelineService.run_mock_pipeline`). */
export function runMockPipeline(
  devUserId: string,
  clinicalSessionId: string,
): Promise<RunPipelineResponse> {
  return apiRequest<RunPipelineResponse>(
    `/api/v1/clinical-sessions/${clinicalSessionId}/run-mock-pipeline`,
    { method: 'POST', devUserId },
  )
}

/** Configurado — respeta el routing real por artifact_type y puede
 * invocar un proveedor LLM externo real (coste real) si así está
 * configurado el backend (ver `AIPipelineService.run_pipeline`). */
export function runPipeline(
  devUserId: string,
  clinicalSessionId: string,
): Promise<RunPipelineResponse> {
  return apiRequest<RunPipelineResponse>(
    `/api/v1/clinical-sessions/${clinicalSessionId}/run-pipeline`,
    { method: 'POST', devUserId },
  )
}

/** Acción explícita, nunca disparada automáticamente por run-pipeline ni
 * run-mock-pipeline (ver `AIPipelineService.propose_anamnesis_update`). */
export function proposeAnamnesisUpdate(
  devUserId: string,
  clinicalSessionId: string,
): Promise<AnamnesisUpdateProposalResponse> {
  return apiRequest<AnamnesisUpdateProposalResponse>(
    `/api/v1/clinical-sessions/${clinicalSessionId}/propose-anamnesis-update`,
    { method: 'POST', devUserId },
  )
}

/** Crea una nueva versión `human_edited` y reabre revisión — ver
 * `AIPipelineService.edit_content()`. */
export function editAIArtifactContent(
  devUserId: string,
  artifactId: string,
  data: ArtifactEditInput,
): Promise<AIArtifact> {
  return apiRequest<AIArtifact>(`/api/v1/ai-artifacts/${artifactId}/content`, {
    method: 'PATCH',
    body: data,
    devUserId,
  })
}

export function listClinicalSessionArtifacts(
  devUserId: string,
  clinicalSessionId: string,
): Promise<AIArtifactListResponse> {
  return apiRequest<AIArtifactListResponse>(
    `/api/v1/clinical-sessions/${clinicalSessionId}/artifacts`,
    { devUserId },
  )
}

export function getAIArtifact(devUserId: string, artifactId: string): Promise<AIArtifact> {
  return apiRequest<AIArtifact>(`/api/v1/ai-artifacts/${artifactId}`, { devUserId })
}

export function listAIArtifactVersions(
  devUserId: string,
  artifactId: string,
): Promise<AIArtifactVersionListResponse> {
  return apiRequest<AIArtifactVersionListResponse>(`/api/v1/ai-artifacts/${artifactId}/versions`, {
    devUserId,
  })
}

export function approveAIArtifact(devUserId: string, artifactId: string): Promise<AIArtifact> {
  return apiRequest<AIArtifact>(`/api/v1/ai-artifacts/${artifactId}/approve`, {
    method: 'POST',
    devUserId,
  })
}

export function rejectAIArtifact(
  devUserId: string,
  artifactId: string,
  rejectionReason?: string,
): Promise<AIArtifact> {
  return apiRequest<AIArtifact>(`/api/v1/ai-artifacts/${artifactId}/reject`, {
    method: 'POST',
    devUserId,
    body: rejectionReason ? { rejection_reason: rejectionReason } : undefined,
  })
}
