import { apiRequest } from './client'
import type { LoginResponse } from './types'

/** `POST /api/v1/auth/login` (Fase 9, hito 9.1) — sin `devUserId`, este
 * endpoint no lo necesita: es el propio punto de entrada de
 * autenticación. */
export function login(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  })
}
