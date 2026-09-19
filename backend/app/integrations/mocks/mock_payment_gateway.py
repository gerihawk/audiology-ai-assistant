"""`MockPaymentGateway`: por defecto (`PAYMENT_GATEWAY=mock`), nunca llama a
Stripe — CLAUDE.md §6. Mismo criterio que `MockTurnstileVerifier`/
`ConsoleEmailSender`: se comporta de forma predecible y determinista para
que el resto del sistema (tests, desarrollo local) funcione sin
credenciales reales.
"""

from __future__ import annotations

import json
import uuid

from app.integrations.domain.payment_gateway import (
    CheckoutSession,
    PortalSession,
    WebhookEvent,
    WebhookSignatureError,
)


class MockPaymentGateway:
    def __init__(self) -> None:
        # Fase 13, hito 13.2 — estado en memoria SOLO para que development/
        # tests puedan simular deriva de estado sin llamar a Stripe de
        # verdad (CLAUDE.md §6): `set_subscription_status` (helper de test,
        # no forma parte del Protocol) lo rellena; `get_subscription_status`
        # devuelve "active" por defecto si nunca se fijó nada, mismo
        # criterio optimista que el resto de Mock* del proyecto.
        self._subscription_statuses: dict[str, str] = {}
        # Última cantidad reportada por suscripción — solo para que un test
        # pueda inspeccionar qué se habría enviado a Stripe.
        self.reported_usage: dict[str, int] = {}

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
        session_id = f"cs_test_mock_{uuid.uuid4().hex[:16]}"
        # URL ficticia, nunca navegable de verdad — igual que
        # `ConsoleEmailSender` "envía" imprimiendo en vez de contactar a un
        # proveedor real. Incluye `price_id`/`clinic_id` como query params
        # solo para que un test o una demo pueda inspeccionar qué se pidió
        # sin tener que llamar a Stripe.
        url = f"{success_url}?mock_checkout=1&session_id={session_id}&clinic_id={clinic_id}"
        return CheckoutSession(url=url, session_id=session_id)

    def construct_webhook_event(self, payload: bytes, signature_header: str) -> WebhookEvent:
        """A diferencia de `StripePaymentGateway`, no verifica ninguna
        firma real (no hay secreto de verdad contra el que verificar en
        development/test) — pero sí exige que `signature_header` no esté
        vacío, para que un test que se olvide de mandar la cabecera falle
        de forma explícita en vez de procesar cualquier payload sin más."""
        if not signature_header:
            raise WebhookSignatureError("Falta la cabecera Stripe-Signature (mock).")
        try:
            body = json.loads(payload)
            return WebhookEvent(id=body["id"], type=body["type"], data=body["data"]["object"])
        except (KeyError, ValueError) as exc:
            raise WebhookSignatureError(f"Payload de webhook (mock) inválido: {exc}") from exc

    def set_subscription_status(self, stripe_subscription_id: str, status: str) -> None:
        """Helper exclusivo de tests — nunca parte del Protocol
        `PaymentGateway` (ver docstring de `__init__`)."""
        self._subscription_statuses[stripe_subscription_id] = status

    async def get_subscription_status(self, stripe_subscription_id: str) -> str:
        return self._subscription_statuses.get(stripe_subscription_id, "active")

    async def report_overage_usage(
        self, *, stripe_customer_id: str, meter_event_name: str, quantity: int
    ) -> None:
        self.reported_usage[stripe_customer_id] = quantity

    async def create_portal_session(
        self, *, stripe_customer_id: str, return_url: str
    ) -> PortalSession:
        return PortalSession(url=f"{return_url}?mock_portal=1&customer_id={stripe_customer_id}")
