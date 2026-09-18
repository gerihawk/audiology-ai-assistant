"""Endpoints /api/v1/billing — Fase 13, hito 13.1.

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
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.billing.api.schemas import CheckoutSessionRequest, CheckoutSessionResponse
from app.billing.service import BillingService
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
