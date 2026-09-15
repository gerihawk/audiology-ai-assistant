"""Tests de integración de invitaciones — Fase 12, hitos 12.2/12.3.

Mismo patrón que test_onboarding_api.py: un `EmailSender` sustituido por
un doble de test para poder leer el token en claro del enlace enviado (la
API nunca lo expone directamente). A diferencia del hito 12.1,
`POST /clinics/{clinic_id}/invitations` SÍ requiere autenticación
(`dev_headers`, ver tests/factories.py) — solo `POST
/invitations/{token}/accept` es superficie pública con su propio límite de
5/minute.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.deps import get_invitation_service
from app.core.rate_limit import limiter
from app.integrations.domain.email_sender import EmailMessage
from app.main import app
from app.onboarding.invitation_service import InvitationService
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository
from tests.factories import ClinicWithUsers, dev_headers

_PASSWORD = "contraseña-de-doce"


class _RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _extract_token_from_link(html_body: str) -> str:
    return html_body.split("token=")[1].split('"')[0]


@pytest_asyncio.fixture
async def invitation_email_sender(
    test_engine: AsyncEngine,
) -> AsyncIterator[_RecordingEmailSender]:
    """Mismo motivo que `onboarding_email_sender` en test_onboarding_api.py."""
    email_sender = _RecordingEmailSender()
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[InvitationService]:
        async with session_factory() as session:
            yield InvitationService(session, email_sender=email_sender)

    app.dependency_overrides[get_invitation_service] = _override
    yield email_sender
    app.dependency_overrides.pop(get_invitation_service, None)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state() -> None:
    """Ver test_auth_api.py — mismo `Limiter` singleton de proceso."""
    limiter.reset()
    yield
    limiter.reset()


async def test_create_invitation_returns_202_and_sends_email(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    response = await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "nueva-companera@test.local", "role": "audiologist"},
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 202, response.text
    assert len(invitation_email_sender.sent) == 1
    assert invitation_email_sender.sent[0].to_email == "nueva-companera@test.local"


async def test_create_invitation_rejects_role_admin_with_422(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "aspirante@test.local", "role": "admin"},
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_create_invitation_rejects_non_admin_with_403(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, role_attr: str
) -> None:
    non_admin = getattr(clinic_with_users, role_attr)

    response = await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "quien-sea@test.local", "role": "viewer"},
        headers=dev_headers(non_admin),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_create_invitation_rejects_mismatched_clinic_with_403(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.post(
        f"/api/v1/clinics/{uuid.uuid4()}/invitations",
        json={"email": "quien-sea@test.local", "role": "viewer"},
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 403


async def test_create_invitation_for_existing_email_still_returns_202(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    """No-enumeración: misma respuesta exista o no ya una cuenta con ese
    email — ver InvitationService.create_invitation."""
    response = await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": clinic_with_users.viewer.email, "role": "audiologist"},
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 202
    assert len(invitation_email_sender.sent) == 1
    assert "accept-invitation?token=" not in invitation_email_sender.sent[0].html_body


async def test_accept_invitation_endpoint_creates_active_user(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    create_response = await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "aceptada@test.local", "role": "viewer"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert create_response.status_code == 202
    raw_token = _extract_token_from_link(invitation_email_sender.sent[0].html_body)

    accept_response = await api_client.post(
        f"/api/v1/invitations/{raw_token}/accept",
        json={"new_password": _PASSWORD, "display_name": "Aceptada"},
    )

    assert accept_response.status_code == 204, accept_response.text
    user = await SqlAlchemyUserRepository().get_by_email(db_session, "aceptada@test.local")
    assert user is not None
    assert user.is_active is True
    assert user.role == Role.VIEWER

    login_response = await api_client.post(
        "/api/v1/auth/login", json={"email": "aceptada@test.local", "password": _PASSWORD}
    )
    assert login_response.status_code == 200


async def test_accept_invitation_endpoint_rejects_unknown_token_with_404(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/invitations/token-inventado/accept",
        json={"new_password": _PASSWORD, "display_name": "Quien Sea"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_accept_invitation_endpoint_returns_429_after_five_requests_per_minute(
    api_client: AsyncClient,
) -> None:
    payload = {"new_password": _PASSWORD, "display_name": "Quien Sea"}
    for _ in range(5):
        response = await api_client.post("/api/v1/invitations/token-inventado/accept", json=payload)
        assert response.status_code == 404

    response = await api_client.post("/api/v1/invitations/token-inventado/accept", json=payload)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


async def test_list_invitations_returns_only_pending(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "pendiente@test.local", "role": "viewer"},
        headers=dev_headers(clinic_with_users.admin),
    )

    response = await api_client.get(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == "pendiente@test.local"
    assert items[0]["role"] == "viewer"
    assert items[0]["is_expired"] is False


async def test_list_invitations_rejects_non_admin_with_403(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.get(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        headers=dev_headers(clinic_with_users.viewer),
    )

    assert response.status_code == 403


async def test_revoke_invitation_endpoint_makes_the_token_unusable(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "a-revocar@test.local", "role": "viewer"},
        headers=dev_headers(clinic_with_users.admin),
    )
    raw_token = _extract_token_from_link(invitation_email_sender.sent[0].html_body)
    list_response = await api_client.get(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        headers=dev_headers(clinic_with_users.admin),
    )
    invitation_id = list_response.json()["items"][0]["id"]

    revoke_response = await api_client.delete(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations/{invitation_id}",
        headers=dev_headers(clinic_with_users.admin),
    )

    assert revoke_response.status_code == 204, revoke_response.text
    accept_response = await api_client.post(
        f"/api/v1/invitations/{raw_token}/accept",
        json={"new_password": _PASSWORD, "display_name": "Demasiado Tarde"},
    )
    assert accept_response.status_code == 409


async def test_revoke_invitation_endpoint_rejects_non_admin_with_403(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    invitation_email_sender: _RecordingEmailSender,
) -> None:
    await api_client.post(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        json={"email": "protegida@test.local", "role": "viewer"},
        headers=dev_headers(clinic_with_users.admin),
    )
    list_response = await api_client.get(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations",
        headers=dev_headers(clinic_with_users.admin),
    )
    invitation_id = list_response.json()["items"][0]["id"]

    response = await api_client.delete(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations/{invitation_id}",
        headers=dev_headers(clinic_with_users.audiologist),
    )

    assert response.status_code == 403


async def test_revoke_invitation_endpoint_rejects_unknown_id_with_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.delete(
        f"/api/v1/clinics/{clinic_with_users.clinic.id}/invitations/{uuid.uuid4()}",
        headers=dev_headers(clinic_with_users.admin),
    )

    assert response.status_code == 404
