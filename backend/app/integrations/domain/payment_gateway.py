"""Puerto `PaymentGateway` (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md §5.

Mismo criterio que `EmailSender`/`TurnstileVerifier`/`TranscriptionProvider`:
interfaz agnóstica del proveedor real, resuelta por configuración vía
`app/integrations/factory.py::build_payment_gateway`. `PAYMENT_GATEWAY=mock`
(por defecto, ver `MockPaymentGateway`) nunca llama a Stripe de verdad —
regla no negociable de CLAUDE.md §6 (Stripe es, literalmente, una API de
pago).

Alcance de este hito: crear una Checkout Session y verificar/parsear un
evento de webhook. `create_portal_session` (hito 13.3) y cualquier llamada
de gestión de suscripción (cambiar de nivel, cancelar) no forman parte de
este puerto todavía — se añaden cuando su hito correspondiente las necesite,
mismo criterio de "no construir infraestructura antes de que un hito
concreto la use" ya aplicado al resto del proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class CheckoutSession:
    #: URL alojada por Stripe a la que redirigir al admin — nunca se
    #: construye una UI de pago propia (docs/fase-13-rfc.md §6, PCI-DSS
    #: SAQ A).
    url: str
    #: Id de la Checkout Session (`cs_...`) — solo para logging/depuración,
    #: nunca se persiste (el webhook es la única fuente de verdad, ver
    #: docs/fase-13-rfc.md §4.1 punto 3).
    session_id: str


@dataclass(slots=True, frozen=True)
class WebhookEvent:
    #: Id del evento de Stripe (`evt_...`) — clave de idempotencia, ver
    #: app/billing/infrastructure/repository.py::SqlAlchemyStripeWebhookEventRepository.
    id: str
    #: p. ej. "checkout.session.completed".
    type: str
    #: `event["data"]["object"]` ya extraído — nunca el evento completo,
    #: para que `BillingService` no tenga que conocer la forma exacta del
    #: payload de Stripe.
    data: dict[str, Any] = field(default_factory=dict)


class WebhookSignatureError(ValueError):
    """La firma `Stripe-Signature` no verifica contra
    `STRIPE_WEBHOOK_SECRET` (o falta) — nunca se procesa un payload en este
    caso, ver docs/fase-13-rfc.md §6."""


class PaymentGateway(Protocol):
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
        """`clinic_id`/`plan` viajan como `client_reference_id`/`metadata`
        de la Checkout Session (redundante a propósito: distintos eventos
        de webhook exponen uno u otro según el objeto de Stripe) — es cómo
        `handle_webhook_event` sabe a qué `Clinic` y a qué nivel aplicar el
        resultado, sin tener que volver a buscar nada por `customer_email`
        (§4.1 punto 4 de docs/fase-13-rfc.md: el estado real nunca se
        confía a lo que el propio cliente afirmó, solo al webhook — pero el
        webhook necesita, aun así, saber qué se pidió)."""
        ...

    def construct_webhook_event(self, payload: bytes, signature_header: str) -> WebhookEvent:
        """Verifica `signature_header` contra el secreto configurado antes
        de parsear nada del `payload` — lanza `WebhookSignatureError` si no
        verifica. Síncrono a propósito: la verificación de firma HMAC no
        hace ninguna llamada de red (a diferencia de `create_checkout_session`),
        mismo criterio que el SDK oficial de Stripe."""
        ...
