"""Puerto `PaymentGateway` (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md §5.

Mismo criterio que `EmailSender`/`TurnstileVerifier`/`TranscriptionProvider`:
interfaz agnóstica del proveedor real, resuelta por configuración vía
`app/integrations/factory.py::build_payment_gateway`. `PAYMENT_GATEWAY=mock`
(por defecto, ver `MockPaymentGateway`) nunca llama a Stripe de verdad —
regla no negociable de CLAUDE.md §6 (Stripe es, literalmente, una API de
pago).

Hito 13.1: crear una Checkout Session y verificar/parsear un evento de
webhook. Hito 13.2 añade `report_overage_usage`/`get_subscription_status`
(ciclo de vida de la suscripción y overage medido); hito 13.3 añade
`create_portal_session` (Stripe Customer Portal) — ver docs/fase-13-rfc.md
§4.2/§5.
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
class PortalSession:
    #: URL alojada por Stripe (Customer Portal) — el admin gestiona su
    #: propio método de pago, ve facturas pasadas y cancela/cambia de nivel
    #: ahí, nunca en una UI propia (docs/fase-13-rfc.md §4.2).
    url: str


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
        metered_price_id: str | None = None,
    ) -> CheckoutSession:
        """`clinic_id`/`plan` viajan como `client_reference_id`/`metadata`
        de la Checkout Session (redundante a propósito: distintos eventos
        de webhook exponen uno u otro según el objeto de Stripe) — es cómo
        `handle_webhook_event` sabe a qué `Clinic` y a qué nivel aplicar el
        resultado, sin tener que volver a buscar nada por `customer_email`
        (§4.1 punto 4 de docs/fase-13-rfc.md: el estado real nunca se
        confía a lo que el propio cliente afirmó, solo al webhook — pero el
        webhook necesita, aun así, saber qué se pidió).

        `metered_price_id` (hito 13.2, opcional): cuando el nivel tiene
        overage definido (ver `app/billing/domain/plans.py`), se añade como
        segunda línea SIN cantidad fija (Stripe la factura según el uso
        reportado por `report_overage_usage`) — así la suscripción resultante
        ya incluye el ítem medido desde el alta, sin tener que modificarla
        más tarde."""
        ...

    def construct_webhook_event(self, payload: bytes, signature_header: str) -> WebhookEvent:
        """Verifica `signature_header` contra el secreto configurado antes
        de parsear nada del `payload` — lanza `WebhookSignatureError` si no
        verifica. Síncrono a propósito: la verificación de firma HMAC no
        hace ninguna llamada de red (a diferencia de `create_checkout_session`),
        mismo criterio que el SDK oficial de Stripe."""
        ...

    async def get_subscription_status(self, stripe_subscription_id: str) -> str:
        """Fase 13, hito 13.2 — consulta el `status` REAL de la Subscription
        en Stripe ("active"/"trialing"/"past_due"/"unpaid"/"canceled"/...),
        usado por `BillingService.reconcile_subscriptions` (cron diario,
        docs/fase-13-rfc.md §6): el respaldo cuando un webhook se pierde y
        `Clinic.subscription_status` queda desactualizado."""
        ...

    async def report_overage_usage(
        self, *, stripe_customer_id: str, meter_event_name: str, quantity: int
    ) -> None:
        """Fase 13, hito 13.2 — reporta el overage acumulado del periodo
        actual a un Stripe Billing Meter (API moderna de uso medido, no la
        `UsageRecord` legacy de `SubscriptionItem`, retirada del SDK).
        `quantity` son CÉNTIMOS de dólar
        (`round(estimated_cost_usd_de_overage * 100)`) — convención
        documentada en docs/fase-13-rfc.md §5. **Requisito de
        configuración en Stripe, fuera del alcance de este código**: el
        Meter (`STRIPE_METER_EVENT_NAME_<NIVEL>`) debe crearse con fórmula
        de agregación "last" (no "sum"), para que reportar el total
        acumulado del periodo cada día sea idempotente en vez de sumarse
        sobre sí mismo — si se crea con "sum" por error, el overage
        facturado quedará multiplicado. `meter_event_name` es el
        `event_name` del Meter, NUNCA un id de Price: son objetos de
        Stripe distintos aunque este RFC los configure para el mismo
        nivel."""
        ...

    async def create_portal_session(
        self, *, stripe_customer_id: str, return_url: str
    ) -> PortalSession:
        """Fase 13, hito 13.3 — Stripe Customer Portal: el admin gestiona su
        propio método de pago, ve facturas pasadas y cancela/cambia de
        nivel ahí, nunca en una UI propia (docs/fase-13-rfc.md §4.2)."""
        ...
