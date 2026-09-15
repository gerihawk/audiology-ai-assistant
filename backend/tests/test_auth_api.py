"""Test de integración de POST /api/v1/auth/login — Fase 9, hito 9.1.
Sin cabecera de autenticación previa: es el propio punto de entrada."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from tests.factories import ClinicWithUsers, create_user

_PASSWORD = "correcta-y-ficticia"


async def test_login_endpoint_returns_bearer_token_for_correct_credentials(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
    )

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": _PASSWORD}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_endpoint_rejects_wrong_password_with_401(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
    )

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "incorrecta"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_login_endpoint_rejects_nonexistent_email_with_401(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": "no-existe@test.local", "password": "cualquiera"}
    )

    assert response.status_code == 401


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state() -> None:
    """El `Limiter` es un singleton en memoria del proceso (Fase 10.5) —
    sin resetearlo, los 5 intentos consumidos por el test de rate limit
    de más abajo contaminarían cualquier otro test de este módulo que se
    ejecute después con la misma IP de origen (`get_remote_address` del
    `TestClient`/`AsyncClient` siempre resuelve a la misma IP simulada)."""
    limiter.reset()
    yield
    limiter.reset()


async def test_login_endpoint_returns_429_after_five_requests_per_minute(
    api_client: AsyncClient,
) -> None:
    for _ in range(5):
        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "no-existe@test.local", "password": "x"}
        )
        assert response.status_code == 401

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": "no-existe@test.local", "password": "x"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
