import type { ApiErrorBody, ApiErrorDetail } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  code: string
  field: string | null
  details: ApiErrorDetail[] | undefined

  constructor(status: number, body: ApiErrorBody | undefined) {
    super(body?.error?.message ?? `Error HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.error?.code ?? 'unknown_error'
    this.field = body?.error?.field ?? null
    this.details = body?.error?.details
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  devUserId?: string | null
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (options.devUserId) {
    headers['X-Dev-User-Id'] = options.devUserId
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : undefined

  if (!response.ok) {
    throw new ApiError(response.status, payload as ApiErrorBody | undefined)
  }

  return payload as T
}
