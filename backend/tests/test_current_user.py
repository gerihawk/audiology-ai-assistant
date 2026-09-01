import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import Settings
from app.core.current_user import JWT_ALGORITHM, FakeCurrentUserProvider, RealCurrentUserProvider
from app.core.exceptions import UnauthenticatedError
from tests.factories import ClinicWithUsers, create_user


def _production_settings(**overrides) -> Settings:
    base = {
        "environment": "production",
        "postgres_user": "u",
        "postgres_password": "s3cret-enough",
        "postgres_db": "d",
        "postgres_host": "h",
        "backend_cors_origins": "https://app.example.com",
        # Fase 9, hito 9.1: baseline válida de production también en
        # AUTH_MODE/JWT_SECRET_KEY — no es lo que este helper prueba.
        "auth_mode": "real",
        "jwt_secret_key": "s3cret-enough-for-jwt-at-least-32-bytes",
    }
    base.update(overrides)
    return Settings(**base)


def _bearer_request(token: str) -> Request:
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    return Request(scope)


def _sign(user_id: uuid.UUID, secret: str, *, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + expires_delta},
        secret,
        algorithm=JWT_ALGORITHM,
    )


def test_fake_current_user_provider_rejects_production() -> None:
    try:
        FakeCurrentUserProvider(_production_settings())
    except RuntimeError as exc:
        assert "production" in str(exc)
    else:
        raise AssertionError("FakeCurrentUserProvider debería rechazar ENVIRONMENT=production")


def test_fake_current_user_provider_rejects_staging() -> None:
    try:
        FakeCurrentUserProvider(_production_settings(environment="staging"))
    except RuntimeError as exc:
        assert "staging" in str(exc)
    else:
        raise AssertionError("FakeCurrentUserProvider debería rechazar ENVIRONMENT=staging")


def test_fake_current_user_provider_allows_development() -> None:
    settings = Settings(
        environment="development",
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        postgres_host="h",
        backend_cors_origins="http://localhost:5173",
    )
    # No debe lanzar.
    FakeCurrentUserProvider(settings)


# --- RealCurrentUserProvider (Fase 9, hito 9.1) ---------------------------

_JWT_SECRET = "test-real-provider-secret-32-bytes-min"


def _real_provider_settings() -> Settings:
    return Settings(
        environment="development",
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        postgres_host="h",
        backend_cors_origins="http://localhost:5173",
        jwt_secret_key=_JWT_SECRET,
    )


async def test_real_current_user_provider_accepts_valid_token(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    provider = RealCurrentUserProvider(_real_provider_settings())
    token = _sign(clinic_with_users.admin.id, _JWT_SECRET, expires_delta=timedelta(hours=8))

    current_user = await provider.get_current_user(_bearer_request(token), db_session)

    assert current_user.id == clinic_with_users.admin.id
    assert current_user.role == clinic_with_users.admin.role


async def test_real_current_user_provider_rejects_expired_token(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    provider = RealCurrentUserProvider(_real_provider_settings())
    token = _sign(clinic_with_users.admin.id, _JWT_SECRET, expires_delta=timedelta(hours=-1))

    with pytest.raises(UnauthenticatedError, match="expirado"):
        await provider.get_current_user(_bearer_request(token), db_session)


async def test_real_current_user_provider_rejects_invalid_signature(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    provider = RealCurrentUserProvider(_real_provider_settings())
    token = _sign(
        clinic_with_users.admin.id,
        "otra-clave-completamente-distinta",
        expires_delta=timedelta(hours=8),
    )

    with pytest.raises(UnauthenticatedError, match="inválido"):
        await provider.get_current_user(_bearer_request(token), db_session)


async def test_real_current_user_provider_rejects_inactive_user(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    inactive = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        is_active=False,
    )
    provider = RealCurrentUserProvider(_real_provider_settings())
    token = _sign(inactive.id, _JWT_SECRET, expires_delta=timedelta(hours=8))

    with pytest.raises(UnauthenticatedError):
        await provider.get_current_user(_bearer_request(token), db_session)


async def test_real_current_user_provider_rejects_nonexistent_user(
    db_session: AsyncSession,
) -> None:
    provider = RealCurrentUserProvider(_real_provider_settings())
    token = _sign(uuid.uuid4(), _JWT_SECRET, expires_delta=timedelta(hours=8))

    with pytest.raises(UnauthenticatedError):
        await provider.get_current_user(_bearer_request(token), db_session)
