"""Tests de integración de /api/v1/billing — Fase 13, hito 13.1.

`POST /billing/checkout-session`: autenticado, solo admin (mismo patrón que
test_integrations_api.py). `POST /billing/webhook`: sin `CurrentUser`,
autenticado por la cabecera `Stripe-Signature` — con `PAYMENT_GATEWAY=mock`
(default de test) esa firma nunca se verifica de verdad
(`MockPaymentGateway`), pero sí debe estar presente.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.billing.service import BillingService
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import get_settings
from app.core.deps import get_billing_service
from app.integrations.mocks.mock_payment_gateway import MockPaymentGateway
from app.main import app
from tests.factories import ClinicWithUsers, dev_headers

_SIGNATURE_HEADER = "t=1,v1=irrelevante-en-mock"


@pytest_asyncio.fixture
async def billing_service_with_prices(test_engine: AsyncEngine) -> AsyncIterator[None]:
    """Sustituye `get_billing_service` por una versión con
    `STRIPE_PRICE_ID_PROFESIONAL` configurado — el `Settings` de test
    (tests/conftest.py) no fija ningún Price real, ver
    tests/test_billing_service.py para el mismo criterio a nivel de
    servicio."""
    settings_with_prices = get_settings().model_copy(
        update={"stripe_price_id_profesional": "price_test_profesional"}
    )
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[BillingService]:
        async with session_factory() as session:
            yield BillingService(
                session, settings=settings_with_prices, payment_gateway=MockPaymentGateway()
            )

    app.dependency_overrides[get_billing_service] = _override
    yield
    app.dependency_overrides.pop(get_billing_service, None)


# --- POST /billing/checkout-session: permisos -----------------------------


async def test_admin_can_create_checkout_session(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    billing_service_with_prices: None,
) -> None:
    response = await api_client.post(
        "/api/v1/billing/checkout-session",
        json={"plan": "profesional"},
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 200, response.text
    assert "mock_checkout=1" in response.json()["checkout_url"]


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_create_checkout_session_forbidden_for_non_admin(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    billing_service_with_prices: None,
    role_attr: str,
) -> None:
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.post(
        "/api/v1/billing/checkout-session",
        json={"plan": "profesional"},
        headers=dev_headers(user),
    )
    assert response.status_code == 403


async def test_create_checkout_session_rejects_unknown_plan(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    billing_service_with_prices: None,
) -> None:
    response = await api_client.post(
        "/api/v1/billing/checkout-session",
        json={"plan": "no-existe"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_create_checkout_session_requires_auth(
    api_client: AsyncClient, billing_service_with_prices: None
) -> None:
    response = await api_client.post(
        "/api/v1/billing/checkout-session", json={"plan": "profesional"}
    )
    assert response.status_code == 401


# --- POST /billing/webhook -------------------------------------------------


async def test_webhook_activates_clinic_subscription(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    clinic_id = clinic_with_users.clinic.id
    payload = {
        "id": "evt_api_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_api",
                "client_reference_id": str(clinic_id),
                "customer": "cus_api_test",
                "subscription": "sub_api_test",
                "metadata": {"clinic_id": str(clinic_id), "plan": "basico"},
            }
        },
    }

    response = await api_client.post(
        "/api/v1/billing/webhook",
        content=json.dumps(payload),
        headers={"stripe-signature": _SIGNATURE_HEADER, "content-type": "application/json"},
    )

    assert response.status_code == 204, response.text
    updated = await SqlAlchemyClinicRepository().get_by_id(db_session, clinic_id)
    assert updated is not None
    assert updated.plan == "basico"
    assert updated.subscription_status == "active"


async def test_webhook_without_signature_header_is_400(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/billing/webhook",
        content=json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {}}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
