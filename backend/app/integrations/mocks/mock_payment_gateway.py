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
    WebhookEvent,
    WebhookSignatureError,
)


class MockPaymentGateway:
    async def create_checkout_session(
        self,
        *,
        clinic_id: str,
        plan: str,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
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
