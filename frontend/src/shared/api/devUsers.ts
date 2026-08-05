import { apiRequest } from './client'
import type { CurrentUser, DevUser } from './types'

export function listDevUsers(): Promise<DevUser[]> {
  return apiRequest<DevUser[]>('/api/v1/dev/users')
}

export function getCurrentUser(devUserId: string): Promise<CurrentUser> {
  return apiRequest<CurrentUser>('/api/v1/me', { devUserId })
}
