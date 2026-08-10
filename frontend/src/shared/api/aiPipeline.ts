import { apiRequest } from './client'
import type {
  AIArtifact,
  AIArtifactListResponse,
  AIArtifactVersionListResponse,
  RunMockPipelineResponse,
} from './types'

export function runMockPipeline(
  devUserId: string,
  clinicalSessionId: string,
): Promise<RunMockPipelineResponse> {
  return apiRequest<RunMockPipelineResponse>(
    `/api/v1/clinical-sessions/${clinicalSessionId}/run-mock-pipeline`,
    { method: 'POST', devUserId },
  )
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
