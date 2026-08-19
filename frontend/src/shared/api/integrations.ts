import { apiRequest } from './client'
import type { IntegrationConfigListResponse } from './types'

export function listIntegrations(devUserId: string): Promise<IntegrationConfigListResponse> {
  return apiRequest<IntegrationConfigListResponse>('/api/v1/integrations', { devUserId })
}
