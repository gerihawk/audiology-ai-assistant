"""BillingService (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md §4.1/§5.

Dos flujos, con criterios de autenticación opuestos (mismo contraste ya
existente entre `OnboardingService.signup_clinic` y
`OnboardingService.verify_email`/`request_password_reset`):

1. `create_checkout_session`: autenticado, solo `ADMIN` de la propia
   clínica (`authorize_billing_action`) — crea una Checkout Session de
   Stripe y devuelve su URL, sin tocar todavía ningún dato de `Clinic`.
2. `handle_webhook_event`: SIN `CurrentUser` — autenticado por la firma
   `Stripe-Signature` (ver `PaymentGateway.construct_webhook_event`), nunca
   por JWT. Es la única fuente de verdad que aplica cambios reales a
   `Clinic.stripe_customer_id`/`subscription_status`/`plan` — el redirect
   de éxito del propio Checkout nunca se usa para eso (§4.1 punto 3 del
   RFC).

Alcance de este hito: solo el evento de alta (`checkout.session.completed`).
El resto del ciclo de vida de la suscripción (impago, cancelación,
actualización) y el gate de acceso por `subscription_status` son el hito
13.2 — un evento no reconocido aquí se registra como procesado sin aplicar
ningún cambio, para que Stripe no lo reintente indefinidamente.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.domain.plans import Plan, PlanNotConfiguredError, resolve_price_id
from app.billing.infrastructure.repository import SqlAlchemyStripeWebhookEventRepository
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.authorization import BillingAction, authorize_billing_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.integrations.domain.payment_gateway import PaymentGateway, WebhookEvent
from app.integrations.factory import build_payment_gateway

logger = logging.getLogger("app.billing")

#: Único tipo de evento aplicado en este hito — ver docstring del módulo.
_HANDLED_EVENT_TYPES = frozenset({"checkout.session.completed"})


@dataclass(slots=True, frozen=True)
class CheckoutSessionResult:
    checkout_url: str


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        webhook_event_repository: SqlAlchemyStripeWebhookEventRepository | None = None,
        payment_gateway: PaymentGateway | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._webhook_events = webhook_event_repository or SqlAlchemyStripeWebhookEventRepository()
        self._gateway = payment_gateway or build_payment_gateway(self._settings)

    async def create_checkout_session(
        self, current_user: CurrentUser, plan: Plan
    ) -> CheckoutSessionResult:
        authorize_billing_action(current_user, BillingAction.CREATE_CHECKOUT_SESSION)

        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        if clinic is None:
            # No debería poder pasar (current_user.clinic_id siempre
            # referencia una Clinic existente) — mismo criterio defensivo
            # que el resto del proyecto ante un estado que la FK ya impide.
            raise NotFoundError("La clínica del usuario actual ya no existe.")

        try:
            price_id = resolve_price_id(self._settings, plan)
        except PlanNotConfiguredError as exc:
            # Nivel válido (ya lo garantiza el `Plan` del schema) pero sin
            # Price de Stripe configurado en este entorno todavía — un 409
            # con el campo `plan` es más útil al frontend que dejarlo subir
            # como 500.
            raise ConflictError(str(exc), field="plan") from exc

        base_url = self._settings.frontend_base_url.rstrip("/")
        checkout = await self._gateway.create_checkout_session(
            clinic_id=str(clinic.id),
            plan=plan.value,
            price_id=price_id,
            customer_email=current_user.email,
            success_url=f"{base_url}/billing/success",
            cancel_url=f"{base_url}/billing/cancel",
        )
        return CheckoutSessionResult(checkout_url=checkout.url)

    async def handle_webhook_event(
        self, raw_payload: bytes, signature_header: str, *, request_id: str | None = None
    ) -> None:
        # `construct_webhook_event` verifica la firma antes de devolver
        # nada — puede lanzar `WebhookSignatureError`, que el router
        # traduce a 400 (ver app/billing/api/router.py).
        event = self._gateway.construct_webhook_event(raw_payload, signature_header)

        if await self._webhook_events.has_processed(self._session, event.id):
            # Reenvío de un evento ya aplicado (Stripe no garantiza entrega
            # única, ver docs/fase-13-rfc.md §5/§6) — no-op silencioso, sin
            # segundo commit ni segunda entrada de auditoría.
            return

        if event.type in _HANDLED_EVENT_TYPES:
            await self._apply_checkout_session_completed(event, request_id=request_id)
        else:
            logger.info(
                "Evento de webhook de Stripe reconocido pero no aplicado en este hito",
                extra={"context": {"event_id": event.id, "event_type": event.type}},
            )

        try:
            await self._webhook_events.mark_processed(self._session, event.id, event.type)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def _apply_checkout_session_completed(
        self, event: WebhookEvent, *, request_id: str | None
    ) -> None:
        checkout_session = event.data
        metadata = checkout_session.get("metadata") or {}
        clinic_id_raw = checkout_session.get("client_reference_id") or metadata.get("clinic_id")
        stripe_customer_id = checkout_session.get("customer")
        stripe_subscription_id = checkout_session.get("subscription")
        plan = metadata.get("plan")

        if not clinic_id_raw or not stripe_customer_id or not stripe_subscription_id or not plan:
            # No debería ocurrir nunca: `create_checkout_session` siempre
            # envía los cuatro (ver StripePaymentGateway/MockPaymentGateway)
            # — si Stripe alguna vez manda un `checkout.session.completed`
            # sin ellos, es una integración rota que debe verse en los
            # logs, no fallar en silencio dejando la Clinic sin activar.
            logger.error(
                "checkout.session.completed sin clinic_id/customer/subscription/plan — "
                "no se aplica ningún cambio",
                extra={
                    "context": {
                        "event_id": event.id,
                        "checkout_session_id": checkout_session.get("id"),
                    }
                },
            )
            return

        clinic_id = uuid.UUID(str(clinic_id_raw))
        updated_clinic = await self._clinics.set_billing_fields(
            self._session,
            clinic_id,
            stripe_customer_id=str(stripe_customer_id),
            stripe_subscription_id=str(stripe_subscription_id),
            # Stripe Checkout con `subscription_data` pero sin periodo de
            # prueba configurado en el propio Price entra directamente en
            # "active"; el estado real y definitivo siempre lo confirma
            # `customer.subscription.updated` (hito 13.2) — este primer
            # valor es solo el que Stripe ya conoce en el momento del
            # checkout.
            subscription_status="active",
            plan=str(plan),
        )
        if updated_clinic is None:
            logger.error(
                "checkout.session.completed referencia una Clinic inexistente",
                extra={"context": {"event_id": event.id, "clinic_id": str(clinic_id)}},
            )
            return

        # Sin entrada en `audit_log`, mismo criterio ya documentado en
        # `UnverifiedClinicCleanupService.purge` (app/onboarding/
        # cleanup_service.py): esa tabla exige `actor_user_id` NOT NULL
        # válido, y aquí no existe ningún usuario humano que haya
        # disparado el cambio (el webhook no tiene `CurrentUser`) — el
        # detalle queda en el log de aplicación, con `event_id` para
        # poder cruzarlo con el dashboard de Stripe si hace falta.
        logger.info(
            "Suscripción activada desde checkout.session.completed",
            extra={
                "context": {
                    "event_id": event.id,
                    "clinic_id": str(clinic_id),
                    "plan": str(plan),
                    "request_id": request_id,
                }
            },
        )
