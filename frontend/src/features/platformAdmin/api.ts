import { ApiError } from '../../shared/api/client'
import type {
  ApiErrorBody,
  PlatformClinic,
  PlatformClinicListResponse,
  PlatformLoginResponse,
  PlatformOperator,
} from '../../shared/api/types'
import { clearPlatformToken, getPlatformToken } from './tokenStore'

/** Envoltorio de `fetch` dedicado a `/api/v1/platform/*` — deliberadamente
 * NO reutiliza `apiRequest` de `shared/api/client.ts`: su `authHeaders()`
 * solo adjunta el token de usuario de clínica, y solo cuando
 * `VITE_AUTH_MODE === 'real'` (ver ese fichero). El operador de plataforma
 * necesita su Authorization: Bearer SIEMPRE que haya un token, con
 * independencia de `VITE_AUTH_MODE` — esta pantalla existe fuera de ese
 * interruptor (ver App.tsx). Misma forma de error (`ApiError`, mismo
 * `core/errors.py` en el backend) para poder reutilizar
 * `describeActionError` sin cambios. */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH'
  body?: unknown
  signal?: AbortSignal
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody | undefined> {
  const contentType = response.headers.get('content-type') ?? ''
  return contentType.includes('application/json')
    ? ((await response.json()) as ApiErrorBody)
    : undefined
}

async function platformApiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getPlatformToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })

  if (!response.ok) {
    // Mismo motivo que `shared/api/client.ts`: un 401 significa que el
    // token de operador ya no sirve (expirado o revocado) — se limpia
    // aquí para que `PlatformAuthContext` reaccione en su siguiente
    // comprobación, sin esperar a una acción explícita de logout.
    if (response.status === 401) clearPlatformToken()
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : undefined
  return payload as T
}

/** `POST /api/v1/platform/auth/login`. */
export function platformLogin(email: string, password: string): Promise<PlatformLoginResponse> {
  return platformApiRequest('/api/v1/platform/auth/login', {
    method: 'POST',
    body: { email, password },
  })
}

/** `POST /api/v1/platform/auth/logout` (hallazgo D1) — revoca en el
 * servidor todos los tokens del operador (204, sin cuerpo). */
export function platformLogout(): Promise<void> {
  return platformApiRequest('/api/v1/platform/auth/logout', { method: 'POST' })
}

/** `GET /api/v1/platform/me` — valida un token persistido en un refresh
 * de página, mismo papel que `GET /api/v1/me` en `AuthContext.tsx`. */
export function getPlatformMe(): Promise<PlatformOperator> {
  return platformApiRequest('/api/v1/platform/me')
}

export function listPlatformClinics(): Promise<PlatformClinicListResponse> {
  return platformApiRequest('/api/v1/platform/clinics')
}

export function setPlatformClinicActive(
  clinicId: string,
  isActive: boolean,
): Promise<PlatformClinic> {
  return platformApiRequest(`/api/v1/platform/clinics/${clinicId}`, {
    method: 'PATCH',
    body: { is_active: isActive },
  })
}
