"""Tests de `BillingService` — Fase 13, hito 13.1 (docs/fase-13-rfc.md).

Permisos (solo admin), resolución de Price por nivel, y aplicación del
único evento de webhook manejado en este hito
(`checkout.session.completed`), incluida su idempotencia.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.domain.plans import Plan
from app.billing.service import BillingService
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError
from app.integrations.mocks.mock_payment_gateway import MockPaymentGateway
from tests.factories import ClinicWithUsers, current_user_from

_SIGNATURE_HEADER = "t=1,v1=irrelevante-en-mock"


def _settings_with_prices():
    return get_settings().model_copy(
        update={
            "stripe_price_id_basico": "price_test_basico",
            "stripe_price_id_profesional": "price_test_profesional",
        }
    )


def _service(db_session: AsyncSession, *, settings=None) -> BillingService:
    return BillingService(
        db_session,
        settings=settings or _settings_with_prices(),
        payment_gateway=MockPaymentGateway(),
    )


def _checkout_completed_payload(
    *, event_id: str, clinic_id: uuid.UUID, plan: str = "profesional"
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "client_reference_id": str(clinic_id),
                    "customer": "cus_test_123",
                    "subscription": "sub_test_123",
                    "metadata": {"clinic_id": str(clinic_id), "plan": plan},
                }
            },
        }
    ).encode("utf-8")


# --- create_checkout_session: permisos -----------------------------------


async def test_admin_can_create_checkout_session(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service = _service(db_session)

    result = await service.create_checkout_session(
        current_user_from(clinic_with_users.admin), Plan.PROFESIONAL
    )

    assert "mock_checkout=1" in result.checkout_url


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_create_checkout_session_forbidden_for_non_admin(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, role_attr: str
) -> None:
    service = _service(db_session)
    user = getattr(clinic_with_users, role_attr)

    with pytest.raises(ForbiddenError):
        await service.create_checkout_session(current_user_from(user), Plan.PROFESIONAL)


async def test_create_checkout_session_with_unconfigured_plan_is_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    # `_settings_with_prices()` no configura STRIPE_PRICE_ID_CLINICA_GRANDE.
    service = _service(db_session)

    with pytest.raises(ConflictError):
        await service.create_checkout_session(
            current_user_from(clinic_with_users.admin), Plan.CLINICA_GRANDE
        )


# --- handle_webhook_event: aplica checkout.session.completed --------------


async def test_webhook_activates_clinic_subscription(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    payload = _checkout_completed_payload(event_id="evt_test_1", clinic_id=clinic_id)

    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.stripe_customer_id == "cus_test_123"
    assert updated.stripe_subscription_id == "sub_test_123"
    assert updated.subscription_status == "active"
    assert updated.plan == "profesional"
    assert updated.sessions_used_this_period == 0


async def test_webhook_is_idempotent_on_repeated_event_id(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    payload = _checkout_completed_payload(event_id="evt_test_repeat", clinic_id=clinic_id)

    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)
    # Segunda entrega del mismo evento (Stripe no garantiza entrega única)
    # — no debe fallar ni volver a aplicar nada distinto.
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.plan == "profesional"


async def test_webhook_unrecognized_event_type_is_noop(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service = _service(db_session)
    clinic_id = clinic_with_users.clinic.id
    payload = json.dumps(
        {
            "id": "evt_test_unhandled",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test_999"}},
        }
    ).encode("utf-8")

    # No debe lanzar — el hito 13.2 gestiona este tipo de evento.
    await service.handle_webhook_event(payload, _SIGNATURE_HEADER)

    unchanged = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert unchanged is not None
    assert unchanged.plan is None


async def test_webhook_missing_signature_header_rejected(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    from app.integrations.domain.payment_gateway import WebhookSignatureError

    service = _service(db_session)
    payload = _checkout_completed_payload(
        event_id="evt_test_nosig", clinic_id=clinic_with_users.clinic.id
    )

    with pytest.raises(WebhookSignatureError):
        await service.handle_webhook_event(payload, "")
