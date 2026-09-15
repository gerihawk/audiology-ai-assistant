"""Tests de integración del onboarding self-service — Fase 12, hito 12.1.

Mismo patrón que test_auth_api.py: superficie sin autenticación previa
(sin X-Dev-User-Id), con su propio límite de 5/minute (ver
app/onboarding/api/router.py) y un `EmailSender` sustituido por un doble
de test — la API nunca expone el token en claro, así que capturar el
enlace enviado es la única forma de probar verify-email/password-reset de
extremo a extremo.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.deps import get_onboarding_service
from app.core.rate_limit import limiter
from app.integrations.domain.email_sender import EmailMessage
from app.main import app
from app.onboarding.service import OnboardingService
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository
from tests.factories import ClinicWithUsers, create_user

_PASSWORD = "contraseña-de-doce"


class _RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _extract_token_from_link(html_body: str) -> str:
    return html_body.split("token=")[1].split('"')[0]


@pytest_asyncio.fixture
async def onboarding_email_sender(
    test_engine: AsyncEngine,
) -> AsyncIterator[_RecordingEmailSender]:
    """Sustituye `get_onboarding_service` por una versión que usa un
    `EmailSender` doble en vez del real (`ConsoleEmailSender`,
    EMAIL_PROVIDER=mock en test) — necesario para leer el token en claro
    del enlace enviado, que la API nunca expone directamente."""
    email_sender = _RecordingEmailSender()
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[OnboardingService]:
        async with session_factory() as session:
            yield OnboardingService(session, email_sender=email_sender)

    app.dependency_overrides[get_onboarding_service] = _override
    yield email_sender
    app.dependency_overrides.pop(get_onboarding_service, None)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state() -> None:
    """Ver test_auth_api.py — mismo `Limiter` singleton de proceso."""
    limiter.reset()
    yield
    limiter.reset()


async def test_signup_endpoint_returns_201_and_creates_inactive_admin(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await api_client.post(
        "/api/v1/clinics/signup",
        json={
            "clinic_name": "Clínica Nueva",
            "admin_email": "nueva-clinica@test.local",
            "admin_display_name": "Admin Nuevo",
            "admin_password": _PASSWORD,
        },
    )

    assert response.status_code == 201, response.text
    user = await SqlAlchemyUserRepository().get_by_email(db_session, "nueva-clinica@test.local")
    assert user is not None
    assert user.is_active is False


async def test_signup_endpoint_rejects_duplicate_email_with_409(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.post(
        "/api/v1/clinics/signup",
        json={
            "clinic_name": "Otra Clínica",
            "admin_email": clinic_with_users.admin.email,
            "admin_display_name": "Alguien",
            "admin_password": _PASSWORD,
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["field"] == "admin_email"


async def test_signup_endpoint_rejects_short_password_with_422(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/clinics/signup",
        json={
            "clinic_name": "Clínica X",
            "admin_email": "corta@test.local",
            "admin_display_name": "Admin",
            "admin_password": "corta",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_signup_endpoint_rejects_blank_clinic_name_with_422(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/clinics/signup",
        json={
            "clinic_name": "   ",
            "admin_email": "blanco@test.local",
            "admin_display_name": "Admin",
            "admin_password": _PASSWORD,
        },
    )

    assert response.status_code == 422


async def test_verify_email_endpoint_activates_user(
    api_client: AsyncClient,
    db_session: AsyncSession,
    onboarding_email_sender: _RecordingEmailSender,
) -> None:
    signup_response = await api_client.post(
        "/api/v1/clinics/signup",
        json={
            "clinic_name": "Clínica Verificable",
            "admin_email": "verificable@test.local",
            "admin_display_name": "Admin",
            "admin_password": _PASSWORD,
        },
    )
    assert signup_response.status_code == 201, signup_response.text
    raw_token = _extract_token_from_link(onboarding_email_sender.sent[0].html_body)

    response = await api_client.post("/api/v1/onboarding/verify-email", json={"token": raw_token})

    assert response.status_code == 204
    user = await SqlAlchemyUserRepository().get_by_email(db_session, "verificable@test.local")
    assert user is not None
    assert user.is_active is True


async def test_verify_email_endpoint_rejects_unknown_token_with_404(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/onboarding/verify-email", json={"token": "no-existe-este-token"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_password_reset_request_always_returns_204(
    api_client: AsyncClient, onboarding_email_sender: _RecordingEmailSender
) -> None:
    """No-enumeración: 204 exista o no la cuenta — mismo criterio que
    AuthService.login."""
    response_unknown = await api_client.post(
        "/api/v1/onboarding/password-reset/request", json={"email": "no-existe@test.local"}
    )
    assert response_unknown.status_code == 204
    assert onboarding_email_sender.sent == []


async def test_password_reset_confirm_endpoint_updates_password(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    onboarding_email_sender: _RecordingEmailSender,
) -> None:
    active_user = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )
    request_response = await api_client.post(
        "/api/v1/onboarding/password-reset/request", json={"email": active_user.email}
    )
    assert request_response.status_code == 204
    raw_token = _extract_token_from_link(onboarding_email_sender.sent[0].html_body)
    new_password = "contraseña-reseteada"

    confirm_response = await api_client.post(
        "/api/v1/onboarding/password-reset/confirm",
        json={"token": raw_token, "new_password": new_password},
    )

    assert confirm_response.status_code == 204
    login_with_new_password = await api_client.post(
        "/api/v1/auth/login", json={"email": active_user.email, "password": new_password}
    )
    assert login_with_new_password.status_code == 200
    login_with_old_password = await api_client.post(
        "/api/v1/auth/login", json={"email": active_user.email, "password": _PASSWORD}
    )
    assert login_with_old_password.status_code == 401


async def test_signup_endpoint_returns_429_after_five_requests_per_minute(
    api_client: AsyncClient,
) -> None:
    payload = {
        "clinic_name": "Clínica Rate Limit",
        "admin_email": "rate-limit@test.local",
        "admin_display_name": "Admin",
        "admin_password": _PASSWORD,
    }
    for _ in range(5):
        response = await api_client.post("/api/v1/clinics/signup", json=payload)
        assert response.status_code in (201, 409)

    response = await api_client.post("/api/v1/clinics/signup", json=payload)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
