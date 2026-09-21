"""Tests de `BillingService` — Fase 13, hito 13.2 (docs/fase-13-rfc.md).

Resto del ciclo de vida del webhook (`customer.subscription.updated`/
`.deleted`, `invoice.paid`/`.payment_failed`), el gate de acceso por
`subscription_status` (`check_active_subscription`), el overage medido
(`report_overage_usage`) y la reconciliación diaria
(`reconcile_subscriptions`). Hito 13.3 (`create_portal_session`/
`get_status`) también vive aquí, por continuidad del mismo módulo.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifactType,
    AIGenerationRun,
    AIGenerationRunStatus,
    AIPipelineRun,
    AIPipelineRunStatus,
)
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.billing.domain.plans import Plan
from app.billing.service import BillingService
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError
from app.integrations.mocks.mock_payment_gateway import MockPaymentGateway
from tests.factories import (
    ClinicWithUsers,
    create_clinical_session,
    create_patient,
    current_user_from,
)

_SIGNATURE_HEADER = "t=1,v1=irrelevante-en-mock"


def _settings_with_overage() -> object:
    return get_settings().model_copy(
        update={
            "stripe_price_id_basico": "price_test_basico",
            "stripe_metered_price_id_basico": "price_test_basico_overage",
            "stripe_meter_event_name_basico": "overage_basico",
            # Tipo de cambio fijo y "redondo" (no el default de
            # `Settings`) para que el test de `report_overage_usage` sea
            # una aritmética verificable a mano, no dependa del valor real
            # de mercado.
            "usd_to_eur_exchange_rate": Decimal("0.8"),
        }
    )


def _service(
    db_session: AsyncSession, *, gateway: MockPaymentGateway | None = None, settings=None
) -> tuple[BillingService, MockPaymentGateway]:
    gw = gateway or MockPaymentGateway()
    return (
        BillingService(
            db_session, settings=settings or _settings_with_overage(), payment_gateway=gw
        ),
        gw,
    )


async def _activate_clinic(
    db_session: AsyncSession,
    clinic_id: uuid.UUID,
    *,
    plan: str = "basico",
    subscription_status: str = "active",
    stripe_customer_id: str = "cus_test",
    stripe_subscription_id: str = "sub_test",
) -> None:
    await SqlAlchemyClinicRepository().set_billing_fields(
        db_session,
        clinic_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        subscription_status=subscription_status,
        plan=plan,
    )
    await db_session.commit()


# --- check_active_subscription: gate de acceso -----------------------------


async def test_gate_allows_clinic_without_stripe_subscription(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Clínica gestionada a mano (sin `subscription_status`) — nunca
    bloqueada, ver docs/fase-13-rfc.md §0.2."""
    service, _ = _service(db_session)
    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_allows_active_subscription(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    await _activate_clinic(db_session, clinic_with_users.clinic.id)
    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


@pytest.mark.parametrize("blocking_status", ["unpaid", "canceled"])
async def test_gate_blocks_definitively_unpaid_or_canceled(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, blocking_status: str
) -> None:
    service, _ = _service(db_session)
    await _activate_clinic(
        db_session, clinic_with_users.clinic.id, subscription_status=blocking_status
    )

    with pytest.raises(ForbiddenError):
        await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_never_blocks_on_first_past_due(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Decisión cerrada del RFC §5: nunca bloquear en `past_due` — Stripe
    todavía reintentando el cobro (dunning)."""
    service, _ = _service(db_session)
    await _activate_clinic(db_session, clinic_with_users.clinic.id, subscription_status="past_due")

    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_blocks_over_safety_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="basico")  # tope 40, techo 80
    repo = SqlAlchemyClinicRepository()
    for _ in range(81):
        await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_allows_under_safety_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="basico")
    repo = SqlAlchemyClinicRepository()
    # Por encima del tope (40) pero por debajo del techo (80): overage, no bloqueo.
    for _ in range(60):
        await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_never_blocks_cadena_empresa_by_usage(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Cadena/Empresa sin tope negociado todavía (`negotiated_included_
    sessions` a None) nunca se bloquea por uso, por muchas sesiones que
    acumule — mismo comportamiento que antes de la ampliación del
    2026-09-21 (docs/fase-13-rfc.md §3.3)."""
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="cadena_empresa")
    repo = SqlAlchemyClinicRepository()
    for _ in range(500):
        await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_blocks_cadena_empresa_over_negotiated_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Ampliación 2026-09-21 (auditoría entre fases): una clínica Cadena/
    Empresa CON tope negociado sí se bloquea al superar su techo de
    seguridad (tope negociado × SAFETY_CAP_MULTIPLIER), igual que
    cualquier otro nivel."""
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="cadena_empresa")
    repo = SqlAlchemyClinicRepository()
    await repo.set_negotiated_included_sessions(
        db_session, clinic_id, negotiated_included_sessions=10
    )
    await db_session.commit()
    for _ in range(21):  # techo = 10 * 2 = 20
        await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.check_active_subscription(current_user_from(clinic_with_users.admin))


async def test_gate_allows_cadena_empresa_under_negotiated_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="cadena_empresa")
    repo = SqlAlchemyClinicRepository()
    await repo.set_negotiated_included_sessions(
        db_session, clinic_id, negotiated_included_sessions=10
    )
    await db_session.commit()
    for _ in range(15):  # por encima del tope (10) pero por debajo del techo (20)
        await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    await service.check_active_subscription(current_user_from(clinic_with_users.admin))


# --- Ciclo de vida del webhook: customer.subscription.* / invoice.* -------


async def test_subscription_updated_syncs_status(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id)

    payload = json.dumps(
        {
            "id": "evt_sub_updated_1",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test", "status": "past_due"}},
        }
    ).encode("utf-8")
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.subscription_status == "past_due"


async def test_subscription_updated_applies_to_all_clinics_sharing_subscription(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Nivel Cadena/Empresa (§3.3): varias `Clinic` comparten el mismo
    `stripe_subscription_id` — el mismo evento debe aplicarse a todas."""
    from app.users.domain.entities import Role
    from tests.factories import create_clinic, create_user

    service, _ = _service(db_session)
    clinic_a = clinic_with_users.clinic
    clinic_b = await create_clinic(db_session)
    await create_user(db_session, clinic_b.id, role=Role.ADMIN)
    await _activate_clinic(db_session, clinic_a.id, plan="cadena_empresa")
    await _activate_clinic(db_session, clinic_b.id, plan="cadena_empresa")

    payload = json.dumps(
        {
            "id": "evt_sub_updated_shared",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test", "status": "unpaid"}},
        }
    ).encode("utf-8")
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    repo = SqlAlchemyClinicRepository()
    for clinic_id in (clinic_a.id, clinic_b.id):
        updated = await repo.get_by_id(db_session, clinic_id)
        assert updated is not None
        assert updated.subscription_status == "unpaid"


async def test_subscription_deleted_sets_canceled(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id)

    payload = json.dumps(
        {
            "id": "evt_sub_deleted_1",
            "type": "customer.subscription.deleted",
            # `status` real de Stripe en este evento no importa: siempre se
            # fija "canceled" explícitamente (ver docstring del handler).
            "data": {"object": {"id": "sub_test", "status": "incomplete_expired"}},
        }
    ).encode("utf-8")
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.subscription_status == "canceled"


async def test_invoice_paid_starts_new_billing_period(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, subscription_status="past_due")
    repo = SqlAlchemyClinicRepository()
    await repo.increment_sessions_used(db_session, clinic_id)
    await repo.increment_sessions_used(db_session, clinic_id)
    await db_session.commit()

    payload = json.dumps(
        {
            "id": "evt_invoice_paid_1",
            "type": "invoice.paid",
            "data": {"object": {"id": "in_test", "subscription": "sub_test"}},
        }
    ).encode("utf-8")
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await repo.get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.subscription_status == "active"
    assert updated.sessions_used_this_period == 0
    assert updated.current_period_started_at is not None


async def test_invoice_payment_failed_does_not_change_status(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Deliberadamente sin cambio de estado — `customer.subscription.updated`
    es quien aplica la transición a `past_due` (ver docstring del handler)."""
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id)

    payload = json.dumps(
        {
            "id": "evt_invoice_failed_1",
            "type": "invoice.payment_failed",
            "data": {"object": {"id": "in_test", "subscription": "sub_test"}},
        }
    ).encode("utf-8")
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.subscription_status == "active"


# --- report_overage_usage ---------------------------------------------------


async def _create_billable_pipeline_run(
    db_session: AsyncSession,
    clinical_session_id: uuid.UUID,
    triggered_by: uuid.UUID,
    *,
    cost_usd: str,
    started_at: datetime,
) -> None:
    pipeline_run = AIPipelineRun(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        triggered_by=triggered_by,
        status=AIPipelineRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=started_at,
        request_id=None,
        is_billable=True,
    )
    await SqlAlchemyAIPipelineRunRepository().add(db_session, pipeline_run)
    generation_run = AIGenerationRun(
        id=uuid.uuid4(),
        ai_pipeline_run_id=pipeline_run.id,
        clinical_session_id=clinical_session_id,
        artifact_type=AIArtifactType.SUMMARY,
        ai_artifact_id=None,
        resulting_version_number=None,
        status=AIGenerationRunStatus.COMPLETED,
        provider_name="mock",
        model_name=None,
        prompt_template_id=None,
        prompt_template_version=None,
        input_token_count=None,
        output_token_count=None,
        estimated_cost_usd=Decimal(cost_usd),
        latency_ms=None,
        execution_time_ms=None,
        rendered_system_prompt=None,
        rendered_user_prompt=None,
        raw_response=None,
        started_at=started_at,
        completed_at=started_at,
        failure_reason=None,
        request_id=None,
    )
    await SqlAlchemyAIGenerationRunRepository().add(db_session, generation_run)


async def test_report_overage_usage_reports_cost_beyond_included_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, gateway = _service(db_session)
    clinic = clinic_with_users.clinic
    admin = clinic_with_users.admin
    await _activate_clinic(db_session, clinic.id, plan="basico")
    # Reduce el tope incluido a un valor manejable en test monkeypatcheando
    # `PLAN_INCLUDED_SESSIONS` sería frágil — en su lugar se crean más
    # sesiones que el tope real de Básico (40) para cruzar el umbral.
    from app.billing.domain import plans as plans_module

    original_caps = dict(plans_module.PLAN_INCLUDED_SESSIONS)
    plans_module.PLAN_INCLUDED_SESSIONS[Plan.BASICO] = 2
    try:
        patient = await create_patient(db_session, clinic.id, admin.id)
        clinical_session = await create_clinical_session(
            db_session, clinic.id, patient.id, admin.id, admin.id
        )
        period_start = datetime.now(UTC) - timedelta(days=1)
        await SqlAlchemyClinicRepository().start_new_billing_period(
            db_session, clinic.id, period_started_at=period_start
        )
        await db_session.commit()

        for i, cost in enumerate(["0.01", "0.02", "0.05", "0.10"]):
            await _create_billable_pipeline_run(
                db_session,
                clinical_session.id,
                admin.id,
                cost_usd=cost,
                started_at=period_start + timedelta(minutes=i),
            )
            repo = SqlAlchemyClinicRepository()
            await repo.increment_sessions_used(db_session, clinic.id)
        await db_session.commit()

        reported = await service.report_overage_usage(clinic.id)

        # Tope=2: las dos últimas ejecuciones (0.05 + 0.10 = 0.15 USD) son
        # overage. `reported` es el coste detectado en USD (sin convertir);
        # lo que se reporta de verdad a Stripe (céntimos de EUR, Price
        # medida denominada en EUR) pasa por `usd_to_eur_exchange_rate`
        # (0.8 en este test) — 0.15 USD * 0.8 = 0.12 EUR = 12 céntimos.
        assert reported == Decimal("0.15")
        assert gateway.reported_usage.get("cus_test") == 12  # céntimos de EUR
    finally:
        plans_module.PLAN_INCLUDED_SESSIONS.clear()
        plans_module.PLAN_INCLUDED_SESSIONS.update(original_caps)


async def test_report_overage_usage_none_within_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, gateway = _service(db_session)
    clinic = clinic_with_users.clinic
    await _activate_clinic(db_session, clinic.id, plan="basico")
    await SqlAlchemyClinicRepository().start_new_billing_period(
        db_session, clinic.id, period_started_at=datetime.now(UTC) - timedelta(days=1)
    )
    await db_session.commit()

    reported = await service.report_overage_usage(clinic.id)

    assert reported is None
    assert gateway.reported_usage == {}


async def test_report_overage_usage_skips_cadena_empresa(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic = clinic_with_users.clinic
    await _activate_clinic(db_session, clinic.id, plan="cadena_empresa")
    await SqlAlchemyClinicRepository().start_new_billing_period(
        db_session, clinic.id, period_started_at=datetime.now(UTC) - timedelta(days=1)
    )
    await db_session.commit()

    assert await service.report_overage_usage(clinic.id) is None


async def test_report_overage_usage_skips_cadena_empresa_even_with_negotiated_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Ampliación 2026-09-21: el tope negociado alimenta el gate de
    acceso, nunca el overage medido de Stripe — ver docstring de
    `BillingService.report_overage_usage`."""
    service, _ = _service(db_session)
    clinic = clinic_with_users.clinic
    await _activate_clinic(db_session, clinic.id, plan="cadena_empresa")
    await SqlAlchemyClinicRepository().set_negotiated_included_sessions(
        db_session, clinic.id, negotiated_included_sessions=10
    )
    await SqlAlchemyClinicRepository().start_new_billing_period(
        db_session, clinic.id, period_started_at=datetime.now(UTC) - timedelta(days=1)
    )
    await db_session.commit()

    assert await service.report_overage_usage(clinic.id) is None


# --- reconcile_subscriptions -------------------------------------------------


async def test_reconcile_corrects_status_drift(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    gateway = MockPaymentGateway()
    service, _ = _service(db_session, gateway=gateway)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, subscription_status="active")
    gateway.set_subscription_status("sub_test", "canceled")

    result = await service.reconcile_subscriptions()

    assert str(clinic_id) in result["reconciled_clinics"]
    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.subscription_status == "canceled"


async def test_reconcile_skips_clinics_without_stripe_subscription(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)

    result = await service.reconcile_subscriptions()

    assert result["checked_clinics"] == []


# --- create_portal_session / get_status (hito 13.3) -------------------------


async def test_create_portal_session_requires_stripe_customer(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)

    with pytest.raises(ConflictError):
        await service.create_portal_session(current_user_from(clinic_with_users.admin))


async def test_create_portal_session_returns_url(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    await _activate_clinic(db_session, clinic_with_users.clinic.id)

    result = await service.create_portal_session(current_user_from(clinic_with_users.admin))

    assert "mock_portal=1" in result.portal_url


async def test_get_status_without_billing(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)

    result = await service.get_status(current_user_from(clinic_with_users.admin))

    assert result.plan is None
    assert result.subscription_status is None
    assert result.included_sessions is None


async def test_get_status_with_active_plan(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    await _activate_clinic(db_session, clinic_with_users.clinic.id, plan="basico")

    result = await service.get_status(current_user_from(clinic_with_users.admin))

    assert result.plan == "basico"
    assert result.included_sessions == 40
    assert result.safety_cap_sessions == 80


async def test_get_status_cadena_empresa_reflects_negotiated_cap(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    await _activate_clinic(db_session, clinic_id, plan="cadena_empresa")
    await SqlAlchemyClinicRepository().set_negotiated_included_sessions(
        db_session, clinic_id, negotiated_included_sessions=10
    )
    await db_session.commit()

    result = await service.get_status(current_user_from(clinic_with_users.admin))

    assert result.plan == "cadena_empresa"
    assert result.included_sessions == 10
    assert result.safety_cap_sessions == 20


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_get_status_forbidden_for_non_admin(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, role_attr: str
) -> None:
    service, _ = _service(db_session)
    user = getattr(clinic_with_users, role_attr)

    with pytest.raises(ForbiddenError):
        await service.get_status(current_user_from(user))
