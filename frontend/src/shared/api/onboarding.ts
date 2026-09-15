import { apiRequest } from './client'
import type { ClinicSignupInput } from './types'

/** Los cuatro endpoints de `app/onboarding/api/router.py` (Fase 12, hito
 * 12.1) — superficie pública, sin `devUserId` ni `Authorization`: mismo
 * criterio que `shared/api/auth.ts::login`. Ninguno devuelve cuerpo
 * (`-> None` en el backend, 201 o 204): `apiRequest` ya maneja los dos
 * casos (204 sin cuerpo, 201 con `null`) sin necesidad de tratarlos aquí. */

export function signupClinic(input: ClinicSignupInput): Promise<void> {
  return apiRequest<void>('/api/v1/clinics/signup', {
    method: 'POST',
    body: input,
  })
}

export function verifyEmail(token: string): Promise<void> {
  return apiRequest<void>('/api/v1/onboarding/verify-email', {
    method: 'POST',
    body: { token },
  })
}

/** Siempre resuelve (204), exista o no la cuenta — no-enumeración, ver
 * `OnboardingService.request_password_reset`. El llamador (
 * `PasswordResetRequestPage`) no debe intentar distinguir los dos casos. */
export function requestPasswordReset(email: string): Promise<void> {
  return apiRequest<void>('/api/v1/onboarding/password-reset/request', {
    method: 'POST',
    body: { email },
  })
}

export function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  return apiRequest<void>('/api/v1/onboarding/password-reset/confirm', {
    method: 'POST',
    body: { token, new_password: newPassword },
  })
}
