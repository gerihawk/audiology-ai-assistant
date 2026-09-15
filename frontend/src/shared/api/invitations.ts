import { apiRequest } from './client'
import type { InvitationAcceptInput, InvitationCreateInput, InvitationListResponse } from './types'

/** Los tres endpoints autenticados de `app/onboarding/api/invitation_router.py`
 * (Fase 12, hito 12.3) — requieren `clinic_id` en la URL (el backend
 * comprueba que coincide con el de `current_user`, ver
 * `authorize_invitation_action`) más `devUserId`/`Authorization` según el
 * modo (`client.ts` añade esto último solo). */

export function createInvitation(
  clinicId: string,
  input: InvitationCreateInput,
  devUserId: string,
): Promise<void> {
  return apiRequest<void>(`/api/v1/clinics/${clinicId}/invitations`, {
    method: 'POST',
    body: input,
    devUserId,
  })
}

export function listInvitations(
  clinicId: string,
  devUserId: string,
): Promise<InvitationListResponse> {
  return apiRequest<InvitationListResponse>(`/api/v1/clinics/${clinicId}/invitations`, {
    devUserId,
  })
}

export function revokeInvitation(
  clinicId: string,
  invitationId: string,
  devUserId: string,
): Promise<void> {
  return apiRequest<void>(`/api/v1/clinics/${clinicId}/invitations/${invitationId}`, {
    method: 'DELETE',
    devUserId,
  })
}

/** Superficie pública — sin `devUserId` ni `Authorization`, mismo criterio
 * que `onboarding.ts` (el token va en la URL, no en cabeceras). */
export function acceptInvitation(token: string, input: InvitationAcceptInput): Promise<void> {
  return apiRequest<void>(`/api/v1/invitations/${token}/accept`, {
    method: 'POST',
    body: input,
  })
}
