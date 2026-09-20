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

Hito 13.1: solo el evento de alta (`checkout.session.completed`). Hito
13.2 (este módulo, ampliado): el resto del ciclo de vida
(`customer.subscription.updated`/`.deleted`, `invoice.paid`/
`.payment_failed`), el gate de acceso por `subscription_status`
(`check_active_subscription`, invocado desde
`app.core.deps.require_active_subscription`), el overage medido
(`report_overage_usage`) y la reconciliación diaria
(`reconcile_subscriptions`) — ver docs/fase-13-rfc.md §4.2/§5/§6. Un
evento de webhook reconocido pero sin handler explícito se registra como
procesado sin aplicar ningún cambio, para que Stripe no lo reintente
indefinidamente.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.generation_run_repository import AIGenerationRunRepository
from app.ai_pipeline.domain.pipeline_run_repository import AIPipelineRunRepository
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.billing.domain.plans import (
    Plan,
    PlanNotConfiguredError,
    included_sessions,
    resolve_meter_event_name,
    resolve_metered_price_id,
    resolve_price_id,
    safety_cap_sessions,
)
from app.billing.infrastructure.repository import SqlAlchemyStripeWebhookEventRepository
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.authorization import BillingAction, authorize_billing_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.integrations.domain.payment_gateway import PaymentGateway, WebhookEvent
from app.integrations.factory import build_payment_gateway

logger = logging.getLogger("app.billing")

#: Eventos de webhook con handler propio en `handle_webhook_event` — el
#: resto se registra como procesado sin aplicar ningún cambio (ver
#: docstring del módulo).
_HANDLED_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
    }
)

#: `subscription_status` que bloquean el acceso (403) vía
#: `check_active_subscription` — decisión cerrada en docs/fase-13-rfc.md
#: §5: nunca en el primer `past_due` (Stripe todavía reintentando el
#: cobro), solo cuando queda definitivamente impagada (`unpaid`) o
#: cancelada (`canceled`).
_BLOCKING_SUBSCRIPTION_STATUSES = frozenset({"unpaid", "canceled"})


@dataclass(slots=True, frozen=True)
class CheckoutSessionResult:
    checkout_url: str


@dataclass(slots=True, frozen=True)
class PortalSessionResult:
    portal_url: str


@dataclass(slots=True, frozen=True)
class BillingStatusResult:
    """Fase 13, hito 13.3 — resumen de facturación de la propia clínica
    para el apartado "Facturación" del frontend. `plan`/`subscription_status`
    `None` significa "gestionada a mano, sin alta de Stripe todavía" (ver
    docs/fase-13-rfc.md §0.2) — el frontend lo distingue para mostrar
    "Contratar un plan" en vez del estado de una suscripción inexistente.
    `included_sessions`/`safety_cap_sessions` son `None` tanto sin plan
    como para Cadena/Empresa (sin tope definido, ver
    `app/billing/domain/plans.py`)."""

    plan: str | None
    subscription_status: str | None
    sessions_used_this_period: int
    included_sessions: int | None
    safety_cap_sessions: int | None
    has_stripe_customer: bool


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        webhook_event_repository: SqlAlchemyStripeWebhookEventRepository | None = None,
        payment_gateway: PaymentGateway | None = None,
        pipeline_run_repository: AIPipelineRunRepository | None = None,
        generation_run_repository: AIGenerationRunRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._webhook_events = webhook_event_repository or SqlAlchemyStripeWebhookEventRepository()
        self._gateway = payment_gateway or build_payment_gateway(self._settings)
        # Fase 13, hito 13.2 — exclusivos de `report_overage_usage`.
        self._pipeline_runs = pipeline_run_repository or SqlAlchemyAIPipelineRunRepository()
        self._generation_runs = generation_run_repository or SqlAlchemyAIGenerationRunRepository()

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

        # Fase 13, hito 13.2: si el nivel tiene overage definido y su Price
        # medido ya está configurado, se añade a la suscripción desde el
        # alta (ver docstring de `PaymentGateway.create_checkout_session`).
        # Ausencia de cualquiera de los dos (nivel sin overage, p. ej.
        # Cadena/Empresa, o Price aún no creado en Stripe) degrada con
        # gracia: la suscripción se crea igualmente, solo sin la línea de
        # overage — nunca bloquea el alta por esto.
        try:
            metered_price_id: str | None = resolve_metered_price_id(self._settings, plan)
        except PlanNotConfiguredError:
            metered_price_id = None

        base_url = self._settings.frontend_base_url.rstrip("/")
        checkout = await self._gateway.create_checkout_session(
            clinic_id=str(clinic.id),
            plan=plan.value,
            price_id=price_id,
            customer_email=current_user.email,
            success_url=f"{base_url}/billing/success",
            cancel_url=f"{base_url}/billing/cancel",
            metered_price_id=metered_price_id,
        )
        return CheckoutSessionResult(checkout_url=checkout.url)

    async def get_status(self, current_user: CurrentUser) -> BillingStatusResult:
        """Fase 13, hito 13.3 — lectura, sin efectos secundarios, para el
        apartado "Facturación" del frontend."""
        authorize_billing_action(current_user, BillingAction.READ_STATUS)

        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        if clinic is None:
            raise NotFoundError("La clínica del usuario actual ya no existe.")

        included: int | None = None
        safety_cap: int | None = None
        if clinic.plan is not None:
            try:
                plan = Plan(clinic.plan)
                included = included_sessions(plan)
                safety_cap = safety_cap_sessions(plan)
            except ValueError:
                pass

        return BillingStatusResult(
            plan=clinic.plan,
            subscription_status=clinic.subscription_status,
            sessions_used_this_period=clinic.sessions_used_this_period,
            included_sessions=included,
            safety_cap_sessions=safety_cap,
            has_stripe_customer=clinic.stripe_customer_id is not None,
        )

    async def create_portal_session(self, current_user: CurrentUser) -> PortalSessionResult:
        """Fase 13, hito 13.3 — Stripe Customer Portal (docs/fase-13-rfc.md
        §4.2): mismo criterio de autorización que `create_checkout_session`
        (ADMIN de la propia clínica)."""
        authorize_billing_action(current_user, BillingAction.CREATE_PORTAL_SESSION)

        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        if clinic is None:
            raise NotFoundError("La clínica del usuario actual ya no existe.")
        if clinic.stripe_customer_id is None:
            # Nunca completó el alta de facturación (`checkout.session.completed`)
            # — no existe ningún `stripe_customer_id` que gestionar todavía.
            raise ConflictError(
                "Esta clínica todavía no tiene una suscripción de Stripe activa.",
                field="plan",
            )

        base_url = self._settings.frontend_base_url.rstrip("/")
        portal = await self._gateway.create_portal_session(
            stripe_customer_id=clinic.stripe_customer_id,
            return_url=f"{base_url}/billing",
        )
        return PortalSessionResult(portal_url=portal.url)

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

        if event.type == "checkout.session.completed":
            await self._apply_checkout_session_completed(event, request_id=request_id)
        elif event.type == "customer.subscription.updated":
            await self._apply_subscription_updated(event, request_id=request_id)
        elif event.type == "customer.subscription.deleted":
            await self._apply_subscription_deleted(event, request_id=request_id)
        elif event.type == "invoice.paid":
            await self._apply_invoice_paid(event, request_id=request_id)
        elif event.type == "invoice.payment_failed":
            await self._apply_invoice_payment_failed(event, request_id=request_id)
        else:
            logger.info(
                "Evento de webhook de Stripe reconocido pero sin handler — no se aplica "
                "ningún cambio",
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

    async def _apply_subscription_updated(
        self, event: WebhookEvent, *, request_id: str | None
    ) -> None:
        """Fase 13, hito 13.2 — sincroniza `Clinic.subscription_status` con
        el `status` real de la Subscription en Stripe (docs/fase-13-rfc.md
        §4.2). Nunca decide aquí si eso bloquea el acceso: esa decisión es
        exclusiva de `check_active_subscription`, evaluada en el momento de
        cada petición, no en el momento del webhook."""
        subscription = event.data
        stripe_subscription_id = subscription.get("id")
        status = subscription.get("status")
        if not stripe_subscription_id or not status:
            logger.error(
                "customer.subscription.updated sin id/status — no se aplica ningún cambio",
                extra={"context": {"event_id": event.id}},
            )
            return
        await self._sync_subscription_status(
            event, str(stripe_subscription_id), str(status), request_id=request_id
        )

    async def _apply_subscription_deleted(
        self, event: WebhookEvent, *, request_id: str | None
    ) -> None:
        """Fase 13, hito 13.2 — `customer.subscription.deleted` es
        definitivo (la Subscription ya no existe en Stripe): se fija
        `subscription_status="canceled"` directamente, sin depender de lo
        que el propio evento reporte en `status` (docs/fase-13-rfc.md §4.2)."""
        subscription = event.data
        stripe_subscription_id = subscription.get("id")
        if not stripe_subscription_id:
            logger.error(
                "customer.subscription.deleted sin id — no se aplica ningún cambio",
                extra={"context": {"event_id": event.id}},
            )
            return
        await self._sync_subscription_status(
            event, str(stripe_subscription_id), "canceled", request_id=request_id
        )

    async def _sync_subscription_status(
        self,
        event: WebhookEvent,
        stripe_subscription_id: str,
        status: str,
        *,
        request_id: str | None,
    ) -> None:
        """Compartido por `_apply_subscription_updated`/
        `_apply_subscription_deleted` — resuelve TODAS las `Clinic` de
        `stripe_subscription_id` (puede ser más de una, ver
        docs/fase-13-rfc.md §3.3, nivel Cadena/Empresa) y aplica el mismo
        `status` a cada una."""
        clinics = await self._clinics.list_by_stripe_subscription_id(
            self._session, stripe_subscription_id
        )
        if not clinics:
            logger.error(
                "Evento de ciclo de vida de suscripción referencia una Clinic inexistente",
                extra={
                    "context": {
                        "event_id": event.id,
                        "stripe_subscription_id": stripe_subscription_id,
                    }
                },
            )
            return
        for clinic in clinics:
            await self._clinics.update_subscription_status(
                self._session, clinic.id, subscription_status=status
            )
        logger.info(
            "subscription_status sincronizado",
            extra={
                "context": {
                    "event_id": event.id,
                    "event_type": event.type,
                    "clinic_ids": [str(clinic.id) for clinic in clinics],
                    "subscription_status": status,
                    "request_id": request_id,
                }
            },
        )

    async def _apply_invoice_paid(self, event: WebhookEvent, *, request_id: str | None) -> None:
        """Fase 13, hito 13.2 — cada factura pagada marca el inicio de un
        nuevo periodo de facturación: reinicia
        `Clinic.sessions_used_this_period` y `current_period_started_at`
        (docs/fase-13-rfc.md §4.2/§5). Usa la hora de recepción del webhook
        como inicio del periodo — aproximación deliberada, suficiente para
        un tope mensual de sesiones (no se parsea `lines`/`period` del
        payload de la factura, que varía según si hay proration)."""
        invoice = event.data
        stripe_subscription_id = invoice.get("subscription")
        if not stripe_subscription_id:
            # Factura no ligada a una suscripción (p. ej. un cargo puntual)
            # — no aplica a este flujo, se registra como procesada sin más.
            return
        clinics = await self._clinics.list_by_stripe_subscription_id(
            self._session, str(stripe_subscription_id)
        )
        if not clinics:
            logger.error(
                "invoice.paid referencia una Clinic inexistente",
                extra={
                    "context": {
                        "event_id": event.id,
                        "stripe_subscription_id": str(stripe_subscription_id),
                    }
                },
            )
            return
        period_started_at = datetime.now(UTC)
        for clinic in clinics:
            await self._clinics.start_new_billing_period(
                self._session, clinic.id, period_started_at=period_started_at
            )
        logger.info(
            "Nuevo periodo de facturación iniciado desde invoice.paid",
            extra={
                "context": {
                    "event_id": event.id,
                    "clinic_ids": [str(clinic.id) for clinic in clinics],
                    "request_id": request_id,
                }
            },
        )

    async def _apply_invoice_payment_failed(
        self, event: WebhookEvent, *, request_id: str | None
    ) -> None:
        """Fase 13, hito 13.2 — deliberadamente SIN cambio de estado: Stripe
        ya envía su propio `customer.subscription.updated` con
        `status="past_due"` cuando corresponde (gestionado por
        `_apply_subscription_updated`) — aplicar aquí además duplicaría la
        misma transición desde dos eventos distintos. Solo se registra para
        observabilidad (docs/fase-13-rfc.md §6, "impago silencioso")."""
        invoice = event.data
        logger.info(
            "Fallo de cobro reportado por Stripe (invoice.payment_failed) — sin cambio de "
            "estado propio, ver customer.subscription.updated",
            extra={
                "context": {
                    "event_id": event.id,
                    "stripe_subscription_id": invoice.get("subscription"),
                    "request_id": request_id,
                }
            },
        )

    async def check_active_subscription(self, current_user: CurrentUser) -> None:
        """Fase 13, hito 13.2 — gate de acceso invocado desde
        `app.core.deps.require_active_subscription` (dependencia FastAPI
        aplicada SOLO a `POST .../run-pipeline`, nunca a
        `run-mock-pipeline`, ver docs/fase-13-rfc.md §5). Dos motivos de
        bloqueo, ambos `ForbiddenError` (403 — el usuario sí está
        autenticado, es su clínica la que no está al día):

        1. `subscription_status` definitivamente impagado/cancelado
           (`_BLOCKING_SUBSCRIPTION_STATUSES`) — nunca en el primer
           `past_due` (§5, dunning de Stripe en curso).
        2. Uso del periodo por encima del techo de seguridad de overage
           (`safety_cap_sessions`) — sin techo definido para Cadena/Empresa,
           nunca bloquea por uso a ese nivel (ver
           `app/billing/domain/plans.py`).

        Una clínica sin `subscription_status` (gestionada a mano, sin alta
        de Stripe todavía — docs/fase-13-rfc.md §0.2) nunca se bloquea
        aquí: ninguna de las dos condiciones aplica sin una suscripción
        real."""
        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        if clinic is None:
            raise NotFoundError("La clínica del usuario actual ya no existe.")

        if clinic.subscription_status is None:
            return

        if clinic.subscription_status in _BLOCKING_SUBSCRIPTION_STATUSES:
            raise ForbiddenError(
                "La suscripción de esta clínica no está al día. Contacta con administración "
                "para regularizarla."
            )

        if clinic.plan is not None:
            try:
                plan = Plan(clinic.plan)
            except ValueError:
                plan = None
            safety_cap = safety_cap_sessions(plan) if plan is not None else None
            if safety_cap is not None and clinic.sessions_used_this_period > safety_cap:
                raise ForbiddenError(
                    "Se ha superado el techo de uso incluido en el nivel contratado. Sube de "
                    "nivel para seguir usando el pipeline de IA."
                )

    async def report_overage_usage(self, clinic_id: uuid.UUID) -> Decimal | None:
        """Fase 13, hito 13.2 (docs/fase-13-rfc.md §4.3/§5) — reporta a
        Stripe el coste de las ejecuciones del pipeline real que superan el
        tope incluido del nivel en el periodo actual. Devuelve el importe
        en USD detectado (antes de convertir a EUR — ver más abajo), o
        `None` si no había nada que reportar (clínica sin plan/periodo,
        nivel sin overage definido, dentro de tope, coste cero, o overage
        sin Meter configurado todavía en este entorno) — usado por
        `reconcile_subscriptions` para resumir qué se reportó. La cantidad
        que de verdad se envía a Stripe (`quantity`, en céntimos) se
        convierte de USD a EUR con `Settings.usd_to_eur_exchange_rate`
        antes de calcularse, porque la Price MEDIDA está denominada en EUR
        mientras que `estimated_cost_usd` siempre está en USD. Sin
        escritura en base de datos: es idempotente por diseño en el lado
        de Stripe (ver docstring de `PaymentGateway.report_overage_usage`),
        así que llamarlo más de una vez al día (p. ej. tras una
        reconciliación manual) es seguro."""
        clinic = await self._clinics.get_by_id(self._session, clinic_id)
        if clinic is None or clinic.plan is None or clinic.stripe_customer_id is None:
            return None
        if clinic.current_period_started_at is None:
            return None
        try:
            plan = Plan(clinic.plan)
        except ValueError:
            return None

        included = included_sessions(plan)
        if included is None:
            # Cadena/Empresa — sin tope ni overage definidos (§3.3).
            return None

        runs = await self._pipeline_runs.list_completed_since_for_clinic(
            self._session, clinic.id, clinic.current_period_started_at
        )
        if len(runs) <= included:
            return None

        overage_run_ids = [run.id for run in runs[included:]]
        overage_cost = await self._generation_runs.sum_estimated_cost_for_pipeline_runs(
            self._session, overage_run_ids
        )
        if overage_cost <= 0:
            return None

        try:
            meter_event_name = resolve_meter_event_name(self._settings, plan)
        except PlanNotConfiguredError:
            logger.info(
                "Overage detectado pero sin Meter de Stripe configurado para este nivel — "
                "no se reporta",
                extra={
                    "context": {
                        "clinic_id": str(clinic.id),
                        "plan": plan.value,
                        "overage_cost_usd": str(overage_cost),
                    }
                },
            )
            return None

        # La Price MEDIDA de Stripe está en EUR (ver
        # `Settings.usd_to_eur_exchange_rate`), pero `overage_cost` viene en
        # USD — se convierte aquí, justo antes de pasar a céntimos, para
        # que el importe que de verdad se factura sea el correcto y no un
        # número de céntimos de USD facturado como si fuesen de EUR.
        overage_cost_eur = overage_cost * self._settings.usd_to_eur_exchange_rate
        quantity_cents = int(
            (overage_cost_eur * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP)
        )
        if quantity_cents <= 0:
            return None

        await self._gateway.report_overage_usage(
            stripe_customer_id=clinic.stripe_customer_id,
            meter_event_name=meter_event_name,
            quantity=quantity_cents,
        )
        logger.info(
            "Overage reportado a Stripe",
            extra={
                "context": {
                    "clinic_id": str(clinic.id),
                    "plan": plan.value,
                    "overage_sessions": len(runs) - included,
                    "overage_cost_usd": str(overage_cost),
                    "usd_to_eur_exchange_rate": str(self._settings.usd_to_eur_exchange_rate),
                    "overage_cost_eur": str(overage_cost_eur),
                    "quantity_cents": quantity_cents,
                }
            },
        )
        return overage_cost

    async def reconcile_subscriptions(self) -> dict[str, list[str]]:
        """Fase 13, hito 13.2 — cron diario (docs/fase-13-rfc.md §6):
        contrasta el `subscription_status` real en Stripe con el guardado
        en cada `Clinic` (respaldo para el caso de un webhook perdido) y,
        de paso, reporta el overage acumulado del periodo de todas las
        clínicas con facturación activa. Invocado desde
        `app.billing.reconcile_cli.main()`/`POST /billing/reconcile`."""
        clinics = await self._clinics.list_with_stripe_subscription(self._session)

        # Cache por `stripe_subscription_id`: el nivel Cadena/Empresa puede
        # traer varias `Clinic` con el mismo id de suscripción (§3.3) — una
        # sola consulta a Stripe por suscripción, no una por clínica.
        status_cache: dict[str, str] = {}
        reconciled_clinics: list[str] = []
        overage_reported_clinics: list[str] = []

        for clinic in clinics:
            assert clinic.stripe_subscription_id is not None  # list_with_stripe_subscription
            if clinic.stripe_subscription_id not in status_cache:
                status_cache[clinic.stripe_subscription_id] = (
                    await self._gateway.get_subscription_status(clinic.stripe_subscription_id)
                )
            real_status = status_cache[clinic.stripe_subscription_id]

            if real_status != clinic.subscription_status:
                await self._clinics.update_subscription_status(
                    self._session, clinic.id, subscription_status=real_status
                )
                reconciled_clinics.append(str(clinic.id))
                logger.info(
                    "Deriva de subscription_status corregida por reconciliación diaria",
                    extra={
                        "context": {
                            "clinic_id": str(clinic.id),
                            "subscription_status_anterior": clinic.subscription_status,
                            "subscription_status_real": real_status,
                        }
                    },
                )

            if await self.report_overage_usage(clinic.id) is not None:
                overage_reported_clinics.append(str(clinic.id))

        await self._session.commit()
        return {
            "checked_clinics": [str(clinic.id) for clinic in clinics],
            "reconciled_clinics": reconciled_clinics,
            "overage_reported_clinics": overage_reported_clinics,
        }
