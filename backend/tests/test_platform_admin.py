"""Tests de la Fase 14 — panel de gestión de clínicas del operador de la
plataforma (`app.platform_admin`). Cubre: login aislado de `platform_operators`
(nunca de `users`), aislamiento de tokens entre los dos mundos (un JWT de
usuario de clínica nunca debe servir aquí, ni al revés), listado/activación
de clínicas, y el gate de acceso por `Clinic.is_active` aplicado en
`get_current_user` (bloquea TODA la superficie autenticada normal, no solo
este panel)."""

from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.current_user import JWT_ALGORITHM
from app.core.rate_limit import limiter
from tests.factories import (
    ClinicWithUsers,
    create_platform_operator,
    create_user,
    dev_headers,
)

_PASSWORD = "correcta-y-ficticia"


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state() -> None:
    """Mismo motivo que en test_auth_api.py: el `Limiter` es un singleton
    en memoria del proceso, hay que aislar los tests de rate limit de
    `/platform/auth/login` del resto de la suite."""
    limiter.reset()
    yield
    limiter.reset()


# --- POST /platform/auth/login --------------------------------------------


async def test_platform_login_returns_bearer_token_for_correct_credentials(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)

    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": _PASSWORD},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(
        body["access_token"], get_settings().jwt_secret_key, algorithms=[JWT_ALGORITHM]
    )
    assert payload["sub"] == str(operator.id)
    assert payload["typ"] == "platform_operator"


async def test_platform_login_rejects_wrong_password_with_401(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)

    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": "incorrecta"},
    )

    assert response.status_code == 401


async def test_platform_login_rejects_inactive_operator(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD, is_active=False)

    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": _PASSWORD},
    )

    assert response.status_code == 401


async def test_platform_login_returns_429_after_five_requests_per_minute(
    api_client: AsyncClient,
) -> None:
    for _ in range(5):
        response = await api_client.post(
            "/api/v1/platform/auth/login",
            json={"email": "no-existe@test.local", "password": "x"},
        )
        assert response.status_code == 401

    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": "no-existe@test.local", "password": "x"},
    )

    assert response.status_code == 429


# --- Aislamiento entre tokens de operador y tokens de usuario de clínica --


async def test_clinic_user_jwt_is_rejected_on_platform_endpoints(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Un JWT firmado por `AuthService` (login normal de clínica) nunca
    debe servir en `/platform/*` — no lleva el claim `typ=platform_operator`
    que `get_current_platform_operator` exige."""
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
    )
    token = await AuthService(db_session).login(user.email, _PASSWORD)

    response = await api_client.get(
        "/api/v1/platform/clinics", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


async def test_platform_operator_jwt_is_rejected_on_normal_user_endpoints(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Simétrico al test anterior: un JWT de operador de plataforma no
    identifica a ningún `User`, así que `RealCurrentUserProvider` nunca
    debe resolverlo como un usuario de clínica válido (aquí se comprueba
    con auth_mode=fake, vía X-Dev-User-Id, que la ruta normal /me exige
    esa cabecera y no acepta un Bearer de operador en su lugar)."""
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    login_response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": _PASSWORD},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


# --- GET/PATCH /platform/clinics ------------------------------------------


async def _operator_headers(api_client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": _PASSWORD},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_get_platform_me_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/platform/me")

    assert response.status_code == 401


async def test_list_clinics_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/platform/clinics")

    assert response.status_code == 401


async def test_get_platform_me_returns_operator_identity(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    response = await api_client.post(
        "/api/v1/platform/auth/login",
        json={"email": operator.email, "password": _PASSWORD},
    )
    token = response.json()["access_token"]

    me_response = await api_client.get(
        "/api/v1/platform/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert me_response.status_code == 200, me_response.text
    body = me_response.json()
    assert body == {
        "id": str(operator.id),
        "email": operator.email,
        "display_name": operator.display_name,
    }


async def test_list_clinics_returns_all_clinics(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    headers = await _operator_headers(api_client, db_session)

    response = await api_client.get("/api/v1/platform/clinics", headers=headers)

    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["items"]]
    assert str(clinic_with_users.clinic.id) in ids


async def test_deactivate_clinic_blocks_its_users_from_the_rest_of_the_api(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    headers = await _operator_headers(api_client, db_session)

    patch_response = await api_client.patch(
        f"/api/v1/platform/clinics/{clinic_with_users.clinic.id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["is_active"] is False

    blocked_response = await api_client.get(
        "/api/v1/me", headers=dev_headers(clinic_with_users.admin)
    )
    assert blocked_response.status_code == 403
    assert blocked_response.json()["error"]["code"] == "forbidden"


async def test_reactivating_clinic_restores_access(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    headers = await _operator_headers(api_client, db_session)
    await api_client.patch(
        f"/api/v1/platform/clinics/{clinic_with_users.clinic.id}",
        json={"is_active": False},
        headers=headers,
    )

    reactivate_response = await api_client.patch(
        f"/api/v1/platform/clinics/{clinic_with_users.clinic.id}",
        json={"is_active": True},
        headers=headers,
    )
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["is_active"] is True

    restored_response = await api_client.get(
        "/api/v1/me", headers=dev_headers(clinic_with_users.admin)
    )
    assert restored_response.status_code == 200


async def test_update_nonexistent_clinic_returns_404(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _operator_headers(api_client, db_session)

    response = await api_client.patch(
        f"/api/v1/platform/clinics/{uuid.uuid4()}",
        json={"is_active": False},
        headers=headers,
    )

    assert response.status_code == 404
