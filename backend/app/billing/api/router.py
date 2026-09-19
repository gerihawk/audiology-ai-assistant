"""Endpoints /api/v1/billing — Fase 13, hitos 13.1/13.2/13.3.

`POST /billing/checkout-session`: superficie autenticada normal (mismo
patrón que `/integrations`), `ADMIN` únicamente (ver
`BillingService.create_checkout_session` -> `authorize_billing_action`).

`POST /billing/webhook`: sin `Depends(get_current_user)` — mismo criterio
que `POST /onboarding/system-cleanup`/`POST /api/v1/retention/system-purge`
(un tercero externo, no un usuario de una clínica, dispara el endpoint),
pero autenticado por firma (`Stripe-Signature` + `STRIPE_WEBHOOK_SECRET`),
no por un secreto compartido en cabecera — el cuerpo se lee siempre como
bytes crudos (`await request.body()`), nunca parseado como JSON por
FastAPI antes de verificar la firma: `stripe.Webhook.construct_event`
necesita el payload exacto tal y como llegó, byte a byte, para poder
verificar el HMAC.

`POST /billing/portal-session` (hito 13.3): igual que `checkout-session`,
`ADMIN` únicamente.

`POST /billing/reconcile` (hito 13.2): mismo patrón que
`POST /onboarding/system-cleanup`/`POST /api/v1/retention/system-purge` —
cron externo diario, autenticado con `X-Billing-Reconcile-Cron-Secret`
(ver `_verify_billing_reconcile_cron_secret` y
`Settings.billing_reconcile_cron_secret`).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.billing.api.schemas import (
    BillingReconcileResponse,
    BillingStatusResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
)
from app.billing.service import BillingService
from app.core.config import get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_billing_service, get_current_user
from app.integrations.domain.payment_gateway import WebhookSignatureError

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> CheckoutSessionResponse:
    result = await service.create_checkout_session(current_user, payload.plan)
    return CheckoutSessionResponse(checkout_url=result.checkout_url)


@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> BillingStatusResponse:
    result = await service.get_status(current_user)
    return BillingStatusResponse(
        plan=result.plan,
        subscription_status=result.subscription_status,
        sessions_used_this_period=result.sessions_used_this_period,
        included_sessions=result.included_sessions,
        safety_cap_sessions=result.safety_cap_sessions,
        has_stripe_customer=result.has_stripe_customer,
    )


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    current_user: CurrentUser = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> PortalSessionResponse:
    result = await service.create_portal_session(current_user)
    return PortalSessionResponse(portal_url=result.portal_url)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def stripe_webhook(
    request: Request,
    service: BillingService = Depends(get_billing_service),
    request_id: str = Depends(get_request_id),
) -> None:
    raw_payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    try:
        await service.handle_webhook_event(raw_payload, signature_header, request_id=request_id)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=400, detail=f"Firma de webhook inválida: {exc}") from exc


async def _verify_billing_reconcile_cron_secret(
    x_billing_reconcile_cron_secret: str | None = Header(
        default=None, alias="X-Billing-Reconcile-Cron-Secret"
    ),
) -> None:
    """Autentica al LLAMADOR del endpoint (un cron externo), no a un
    usuario — ver `Settings.billing_reconcile_cron_secret`.
    `secrets.compare_digest`, nunca `==`, mismo criterio que
    `app.retention.api.router._verify_retention_cron_secret`/
    `app.onboarding.api.router._verify_onboarding_cleanup_cron_secret`."""
    expected = get_settings().billing_reconcile_cron_secret
    if x_billing_reconcile_cron_secret is None or not secrets.compare_digest(
        x_billing_reconcile_cron_secret, expected
    ):
        raise HTTPException(
            status_code=401, detail="X-Billing-Reconcile-Cron-Secret ausente o inválida."
        )


@router.post("/reconcile", response_model=BillingReconcileResponse)
async def reconcile_subscriptions(
    _: None = Depends(_verify_billing_reconcile_cron_secret),
    service: BillingService = Depends(get_billing_service),
) -> BillingReconcileResponse:
    result = await service.reconcile_subscriptions()
    return BillingReconcileResponse(**result)
