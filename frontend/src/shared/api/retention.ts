import { apiRequest } from './client'
import type { AudioRecordingListResponse } from './types'

export function listExpiredAudio(devUserId: string): Promise<AudioRecordingListResponse> {
  return apiRequest<AudioRecordingListResponse>('/api/v1/retention/expired-audio', { devUserId })
}

export function purgeExpiredAudio(devUserId: string): Promise<AudioRecordingListResponse> {
  return apiRequest<AudioRecordingListResponse>('/api/v1/retention/expired-audio/purge', {
    method: 'POST',
    devUserId,
  })
}
