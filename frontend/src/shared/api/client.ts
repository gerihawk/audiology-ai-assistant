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

/** Parsea el cuerpo de error del backend (JSON, mismo formato en todos los
 * endpoints — ver `core/errors.py`) — compartido por `apiRequest` y
 * `apiDownload`: es la única pieza realmente duplicada entre una llamada
 * JSON y una binaria, ambas pueden fallar con el mismo `error.code`. */
async function parseErrorBody(response: Response): Promise<ApiErrorBody | undefined> {
  const contentType = response.headers.get('content-type') ?? ''
  return contentType.includes('application/json')
    ? ((await response.json()) as ApiErrorBody)
    : undefined
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

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : undefined
  return payload as T
}

export interface DownloadOptions {
  devUserId?: string | null
  signal?: AbortSignal
}

export interface DownloadResult {
  blob: Blob
  /** Nombre de fichero tomado de `Content-Disposition` — `null` solo si el
   * backend no lo envía (nunca se reconstruye aquí; ver
   * `ai_pipeline/api/router.py`/`clinical_record/api/router.py`, que
   * siempre lo fijan en un `200`). */
  filename: string | null
}

const CONTENT_DISPOSITION_FILENAME_RE = /filename="?([^";]+)"?/i

function extractFilename(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null
  const match = CONTENT_DISPOSITION_FILENAME_RE.exec(contentDisposition)
  return match ? match[1] : null
}

/** Igual que `apiRequest`, pero para respuestas binarias (exportación
 * PDF/texto) — mismo `BASE_URL`, mismo header `X-Dev-User-Id`, mismo
 * parseo de error JSON del backend (`parseErrorBody`). Siempre `GET`, sin
 * `body`: los dos endpoints de exportación actuales solo leen. Nunca usar
 * para JSON — para eso sigue siendo `apiRequest`. */
export async function apiDownload(
  path: string,
  options: DownloadOptions = {},
): Promise<DownloadResult> {
  const headers: Record<string, string> = {}
  if (options.devUserId) {
    headers['X-Dev-User-Id'] = options.devUserId
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'GET',
    headers,
    signal: options.signal,
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  const blob = await response.blob()
  const filename = extractFilename(response.headers.get('content-disposition'))
  return { blob, filename }
}
