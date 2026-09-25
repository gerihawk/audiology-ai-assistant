"""Revocación de JWT en servidor — hallazgo bajo D1 del red team
(docs/security/red-team-app-2026-09-22.md). Cubre los dos mundos de
identidad: usuario de clínica (`RealCurrentUserProvider`) y operador de
plataforma (`get_current_platform_operator`)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.audit_log.infrastructure.orm import AuditLogORM
from app.core.config import get_settings
from app.core.current_user import JWT_ALGORITHM, RealCurrentUserProvider
from app.core.deps import get_current_user_provider
from app.core.rate_limit import limiter
from app.integrations.domain.email_sender import EmailMessage
from app.main import app
from app.onboarding.service import OnboardingService
from app.platform_admin import cli as platform_cli
from app.platform_admin.service import PLATFORM_TOKEN_TYPE
from app.users.domain.entities import Role, User
from tests.factories import ClinicWithUsers, create_platform_operator, create_user

_PASSWORD = "correcta-y-ficticia"


@pytest.fixture(autouse=True)
def _real_auth_and_clean_limiter() -> Iterator[None]:
    """`api_client` resuelve por defecto `FakeCurrentUserProvider`
    (X-Dev-User-Id): aquí hace falta el JWT real. Y el limiter en memoria
    se resetea por el mismo motivo que en test_auth_api.py."""
    app.dependency_overrides[get_current_user_provider] = lambda: RealCurrentUserProvider(
        get_settings()
    )
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.pop(get_current_user_provider, None)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sign_without_tv(sub: uuid.UUID, *, expires_delta: timedelta, **extra: str) -> str:
    """Token con la forma de los emitidos antes del deploy de D1 (sin `tv`)."""
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(sub), "iat": now, "exp": now + expires_delta, **extra},
        get_settings().jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )


async def _login(api_client: AsyncClient, path: str, email: str) -> str:
    response = await api_client.post(path, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


# --- Usuario de clínica -----------------------------------------------------


async def _clinic_user(db_session: AsyncSession, clinic_with_users: ClinicWithUsers) -> User:
    return await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )


async def test_logout_revokes_token_with_same_401_as_expired(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await _clinic_user(db_session, clinic_with_users)
    token = await _login(api_client, "/api/v1/auth/login", user.email)
    assert (await api_client.get("/api/v1/me", headers=_bearer(token))).status_code == 200

    logout = await api_client.post("/api/v1/auth/logout", headers=_bearer(token))
    assert logout.status_code == 204, logout.text
    assert logout.content == b""

    revoked = await api_client.get("/api/v1/me", headers=_bearer(token))
    expired = await api_client.get(
        "/api/v1/me", headers=_bearer(_sign_without_tv(user.id, expires_delta=timedelta(hours=-1)))
    )
    assert revoked.status_code == expired.status_code == 401
    assert revoked.json()["error"] == expired.json()["error"]

    # Un login nuevo emite un token con la versión vigente y vuelve a valer.
    fresh = await _login(api_client, "/api/v1/auth/login", user.email)
    assert (await api_client.get("/api/v1/me", headers=_bearer(fresh))).status_code == 200


async def test_logout_writes_audit_entry_without_metadata(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    test_engine: AsyncEngine,
) -> None:
    user = await _clinic_user(db_session, clinic_with_users)
    token = await _login(api_client, "/api/v1/auth/login", user.email)

    await api_client.post("/api/v1/auth/logout", headers=_bearer(token))

    async with async_sessionmaker(bind=test_engine)() as session:
        result = await session.execute(
            select(AuditLogORM).where(AuditLogORM.actor_user_id == user.id)
        )
        rows = result.scalars().all()
    assert [(r.action, r.entity_type, r.entity_id, r.audit_metadata) for r in rows] == [
        ("auth.logout", "user", user.id, {})
    ]


async def test_logout_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/auth/logout")
    assert response.status_code == 401


class _RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


async def test_password_reset_revokes_existing_token(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await _clinic_user(db_session, clinic_with_users)
    token = await _login(api_client, "/api/v1/auth/login", user.email)

    email_sender = _RecordingEmailSender()
    service = OnboardingService(db_session, email_sender=email_sender)
    await service.request_password_reset(user.email)
    raw_token = email_sender.sent[0].html_body.split("token=")[1].split('"')[0]
    await service.confirm_password_reset(raw_token, "nueva-contraseña-ficticia")

    response = await api_client.get("/api/v1/me", headers=_bearer(token))
    assert response.status_code == 401


async def test_token_without_tv_is_valid_while_version_is_zero(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await _clinic_user(db_session, clinic_with_users)
    legacy = _sign_without_tv(user.id, expires_delta=timedelta(hours=8))

    assert (await api_client.get("/api/v1/me", headers=_bearer(legacy))).status_code == 200

    # Tras el primer logout (versión 1), el token legado deja de valer.
    logout = await api_client.post("/api/v1/auth/logout", headers=_bearer(legacy))
    assert logout.status_code == 204
    assert (await api_client.get("/api/v1/me", headers=_bearer(legacy))).status_code == 401


async def test_logout_of_one_user_does_not_affect_another(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    alice = await _clinic_user(db_session, clinic_with_users)
    bob = await _clinic_user(db_session, clinic_with_users)
    alice_token = await _login(api_client, "/api/v1/auth/login", alice.email)
    bob_token = await _login(api_client, "/api/v1/auth/login", bob.email)

    await api_client.post("/api/v1/auth/logout", headers=_bearer(alice_token))

    assert (await api_client.get("/api/v1/me", headers=_bearer(alice_token))).status_code == 401
    assert (await api_client.get("/api/v1/me", headers=_bearer(bob_token))).status_code == 200


# --- Operador de plataforma -------------------------------------------------


async def test_platform_logout_revokes_token_with_same_401_as_expired(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    token = await _login(api_client, "/api/v1/platform/auth/login", operator.email)
    assert (await api_client.get("/api/v1/platform/me", headers=_bearer(token))).status_code == 200

    logout = await api_client.post("/api/v1/platform/auth/logout", headers=_bearer(token))
    assert logout.status_code == 204, logout.text

    revoked = await api_client.get("/api/v1/platform/me", headers=_bearer(token))
    expired_token = _sign_without_tv(
        operator.id, expires_delta=timedelta(hours=-1), typ=PLATFORM_TOKEN_TYPE
    )
    expired = await api_client.get("/api/v1/platform/me", headers=_bearer(expired_token))
    assert revoked.status_code == expired.status_code == 401
    assert revoked.json()["error"] == expired.json()["error"]


async def test_platform_password_reset_revokes_existing_token(
    api_client: AsyncClient,
    db_session: AsyncSession,
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    token = await _login(api_client, "/api/v1/platform/auth/login", operator.email)
    monkeypatch.setattr(
        platform_cli,
        "get_session_factory",
        lambda: async_sessionmaker(bind=test_engine, expire_on_commit=False),
    )

    await platform_cli.reset_password(operator.email, "otra-contraseña-ficticia")

    response = await api_client.get("/api/v1/platform/me", headers=_bearer(token))
    assert response.status_code == 401


async def test_platform_token_without_tv_is_valid_while_version_is_zero(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await create_platform_operator(db_session, password=_PASSWORD)
    legacy = _sign_without_tv(
        operator.id, expires_delta=timedelta(hours=2), typ=PLATFORM_TOKEN_TYPE
    )

    response = await api_client.get("/api/v1/platform/me", headers=_bearer(legacy))
    assert response.status_code == 200


async def test_platform_logout_of_one_operator_does_not_affect_another(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    first = await create_platform_operator(db_session, password=_PASSWORD)
    second = await create_platform_operator(db_session, password=_PASSWORD)
    first_token = await _login(api_client, "/api/v1/platform/auth/login", first.email)
    second_token = await _login(api_client, "/api/v1/platform/auth/login", second.email)

    await api_client.post("/api/v1/platform/auth/logout", headers=_bearer(first_token))

    first_me = await api_client.get("/api/v1/platform/me", headers=_bearer(first_token))
    second_me = await api_client.get("/api/v1/platform/me", headers=_bearer(second_token))
    assert first_me.status_code == 401
    assert second_me.status_code == 200
