import { apiRequest } from './client'
import type { BillingStatus, CheckoutSessionResponse, Plan, PortalSessionResponse } from './types'

/** Los cuatro endpoints de `app/billing/api/router.py` (Fase 13, hitos
 * 13.1/13.2/13.3) que el frontend usa — `POST /billing/webhook` es
 * exclusivo de Stripe, nunca llamado desde aquí. Todos `ADMIN` únicamente
 * (ver `authorize_billing_action`), igual que `invitations.ts`. */

export function getBillingStatus(devUserId: string): Promise<BillingStatus> {
  return apiRequest<BillingStatus>('/api/v1/billing/status', { devUserId })
}

export function createCheckoutSession(
  plan: Plan,
  devUserId: string,
): Promise<CheckoutSessionResponse> {
  return apiRequest<CheckoutSessionResponse>('/api/v1/billing/checkout-session', {
    method: 'POST',
    body: { plan },
    devUserId,
  })
}

export function createPortalSession(devUserId: string): Promise<PortalSessionResponse> {
  return apiRequest<PortalSessionResponse>('/api/v1/billing/portal-session', {
    method: 'POST',
    devUserId,
  })
}
