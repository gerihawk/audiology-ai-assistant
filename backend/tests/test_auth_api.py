"""Test de integración de POST /api/v1/auth/login — Fase 9, hito 9.1.
Sin cabecera de autenticación previa: es el propio punto de entrada."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
