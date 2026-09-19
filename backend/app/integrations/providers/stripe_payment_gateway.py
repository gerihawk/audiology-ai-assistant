"""`StripePaymentGateway`: implementación real de `PaymentGateway` (Fase 13,
hito 13.1) sobre el SDK oficial `stripe` — ver docs/fase-13-rfc.md §5.

`create_checkout_session` usa `create_async` (soporte nativo del SDK desde
v15, sobre httpx) en vez de bloquear el event loop con la llamada síncrona
por defecto — mismo motivo por el que `AssemblyAITranscriptionProvider`/
`DeepgramTranscriptionProvider` usan `httpx.AsyncClient` en vez de un
cliente síncrono.
"""

from __future__ import annotations

import stripe

from app.integrations.domain.payment_gateway import (
    CheckoutSession,
    PortalSession,
    WebhookEvent,
    WebhookSignatureError,
)


class StripePaymentGateway:
    def __init__(self, *, api_key: str | None, webhook_secret: str | None) -> None:
        if not api_key:
            raise ValueError(
                "STRIPE_SECRET_KEY es obligatoria para usar StripePaymentGateway "
                "(PAYMENT_GATEWAY=stripe)."
            )
        if not webhook_secret:
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET es obligatoria para usar StripePaymentGateway "
                "(PAYMENT_GATEWAY=stripe): sin ella no se puede verificar la firma de "
                "POST /billing/webhook."
            )
        self._api_key = api_key
        self._webhook_secret = webhook_secret

    async def create_checkout_session(
        self,
        *,
        clinic_id: str,
        plan: str,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metered_price_id: str | None = None,
    ) -> CheckoutSession:
        line_items: list[dict[str, object]] = [{"price": price_id, "quantity": 1}]
        if metered_price_id:
            # Fase 13, hito 13.2 — línea de overage SIN `quantity`: un Price
            # con `recurring.usage_type=metered` la rechaza si se envía
            # cantidad fija (Stripe la deriva del uso reportado, ver
            # `report_overage_usage`).
            line_items.append({"price": metered_price_id})
        session = await stripe.checkout.Session.create_async(
            api_key=self._api_key,
            mode="subscription",
            line_items=line_items,
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            # Redundante a propósito (ver docstring de
            # `PaymentGateway.create_checkout_session`): `client_reference_id`
            # aparece directamente en el evento `checkout.session.completed`;
            # `metadata` se propaga además a la `Subscription` resultante,
            # útil para eventos posteriores del ciclo de vida (hito 13.2).
            client_reference_id=clinic_id,
            metadata={"clinic_id": clinic_id, "plan": plan},
            subscription_data={"metadata": {"clinic_id": clinic_id, "plan": plan}},
        )
        assert session.url is not None  # Stripe siempre lo devuelve en modo `subscription`
        return CheckoutSession(url=session.url, session_id=session.id)

    def construct_webhook_event(self, payload: bytes, signature_header: str) -> WebhookEvent:
        try:
            event = stripe.Webhook.construct_event(payload, signature_header, self._webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise WebhookSignatureError(str(exc)) from exc
        return WebhookEvent(id=event["id"], type=event["type"], data=event["data"]["object"])

    async def get_subscription_status(self, stripe_subscription_id: str) -> str:
        subscription = await stripe.Subscription.retrieve_async(
            stripe_subscription_id, api_key=self._api_key
        )
        return subscription.status

    async def report_overage_usage(
        self, *, stripe_customer_id: str, meter_event_name: str, quantity: int
    ) -> None:
        # API moderna de Stripe Billing Meters (la `UsageRecord` legacy de
        # `SubscriptionItem` ya no existe en este SDK) — ver docstring del
        # Protocol sobre el requisito de agregación "last" en el Meter.
        await stripe.billing.MeterEvent.create_async(
            api_key=self._api_key,
            event_name=meter_event_name,
            payload={"stripe_customer_id": stripe_customer_id, "value": str(quantity)},
        )

    async def create_portal_session(
        self, *, stripe_customer_id: str, return_url: str
    ) -> PortalSession:
        portal_session = await stripe.billing_portal.Session.create_async(
            api_key=self._api_key,
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return PortalSession(url=portal_session.url)
