"""Tests de OnboardingService — Fase 12, hito 12.1. Mismo criterio de
no-enumeración que test_auth_service.py para request_password_reset
(siempre silencioso, exista o no la cuenta)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.integrations.domain.email_sender import EmailMessage
from app.onboarding.service import ClinicSignupData, OnboardingService
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository
from tests.factories import ClinicWithUsers, create_user

_PASSWORD = "contraseña-de-doce"


class _RecordingEmailSender:
    """Doble de test de `EmailSender` — nunca contacta un proveedor real,
    solo guarda los mensajes para que el test los inspeccione."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _make_service(session: AsyncSession) -> tuple[OnboardingService, _RecordingEmailSender]:
    email_sender = _RecordingEmailSender()
    service = OnboardingService(session, email_sender=email_sender)
    return service, email_sender


def _extract_token_from_link(html_body: str) -> str:
    return html_body.split("token=")[1].split('"')[0]


async def test_signup_clinic_creates_inactive_admin_and_sends_verification_email(
    db_session: AsyncSession,
) -> None:
    service, email_sender = _make_service(db_session)

    await service.signup_clinic(
        ClinicSignupData(
            clinic_name="  Clínica Auditiva Vila-real  ",
            admin_email="  Admin@Ejemplo.com ",
            admin_display_name="  Gerard  ",
            admin_password=_PASSWORD,
        )
    )

    user = await SqlAlchemyUserRepository().get_by_email(db_session, "admin@ejemplo.com")
    assert user is not None
    assert user.is_active is False
    assert user.role == Role.ADMIN
    assert user.display_name == "Gerard"

    assert len(email_sender.sent) == 1
    sent = email_sender.sent[0]
    assert sent.to_email == "admin@ejemplo.com"
    assert "verify-email?token=" in sent.html_body


async def test_signup_clinic_with_already_registered_email_raises_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _make_service(db_session)

    with pytest.raises(ConflictError) as exc_info:
        await service.signup_clinic(
            ClinicSignupData(
                clinic_name="Otra Clínica",
                admin_email=clinic_with_users.admin.email,
                admin_display_name="Alguien",
                admin_password=_PASSWORD,
            )
        )

    assert exc_info.value.field == "admin_email"


async def test_verify_email_activates_user_and_consumes_token(
    db_session: AsyncSession,
) -> None:
    service, email_sender = _make_service(db_session)
    await service.signup_clinic(
        ClinicSignupData(
            clinic_name="Clínica de Test",
            admin_email="pending@test.local",
            admin_display_name="Pendiente",
            admin_password=_PASSWORD,
        )
    )
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)

    await service.verify_email(raw_token)

    activated = await SqlAlchemyUserRepository().get_by_email(db_session, "pending@test.local")
    assert activated is not None
    assert activated.is_active is True


async def test_verify_email_with_invalid_token_raises_not_found(
    db_session: AsyncSession,
) -> None:
    service, _ = _make_service(db_session)

    with pytest.raises(NotFoundError):
        await service.verify_email("token-inventado-que-no-existe")


async def test_verify_email_with_already_used_token_raises_conflict(
    db_session: AsyncSession,
) -> None:
    service, email_sender = _make_service(db_session)
    await service.signup_clinic(
        ClinicSignupData(
            clinic_name="Clínica de Test",
            admin_email="pending2@test.local",
            admin_display_name="Pendiente",
            admin_password=_PASSWORD,
        )
    )
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)
    await service.verify_email(raw_token)

    with pytest.raises(ConflictError):
        await service.verify_email(raw_token)


async def test_confirm_password_reset_updates_password_hash(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    active_user = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )
    service, email_sender = _make_service(db_session)
    await service.request_password_reset(active_user.email)
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)

    await service.confirm_password_reset(raw_token, "nueva-contraseña-12")

    refreshed = await SqlAlchemyUserRepository().get_by_email(db_session, active_user.email)
    assert refreshed is not None
    assert refreshed.password_hash != active_user.password_hash


async def test_request_password_reset_is_silent_for_nonexistent_email(
    db_session: AsyncSession,
) -> None:
    service, email_sender = _make_service(db_session)

    await service.request_password_reset("no-existe@test.local")

    assert email_sender.sent == []


async def test_request_password_reset_is_silent_for_inactive_user(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    inactive_user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=Role.AUDIOLOGIST,
        password=_PASSWORD,
        is_active=False,
    )
    service, email_sender = _make_service(db_session)

    await service.request_password_reset(inactive_user.email)

    assert email_sender.sent == []


async def test_request_password_reset_issues_usable_token_and_sends_email(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    active_user = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )
    service, email_sender = _make_service(db_session)

    await service.request_password_reset(active_user.email)

    assert len(email_sender.sent) == 1
    assert email_sender.sent[0].to_email == active_user.email
    assert "reset-password?token=" in email_sender.sent[0].html_body


async def test_confirm_password_reset_with_reused_token_raises_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    active_user = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )
    service, email_sender = _make_service(db_session)
    await service.request_password_reset(active_user.email)
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)

    await service.confirm_password_reset(raw_token, "otra-contraseña-larga")

    with pytest.raises(ConflictError):
        await service.confirm_password_reset(raw_token, "tercera-contraseña-x")


async def test_issuing_a_second_token_invalidates_the_first(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Reenviar la verificación (o pedir un segundo reseteo) invalida el
    enlace anterior — solo el último enviado por email sigue siendo
    válido."""
    active_user = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, password=_PASSWORD
    )
    service, email_sender = _make_service(db_session)

    await service.request_password_reset(active_user.email)
    first_token = _extract_token_from_link(email_sender.sent[0].html_body)
    await service.request_password_reset(active_user.email)
    second_token = _extract_token_from_link(email_sender.sent[1].html_body)

    assert first_token != second_token
    with pytest.raises(ConflictError):
        await service.confirm_password_reset(first_token, "contraseña-valida-1")

    # El segundo (el último enviado) sigue siendo válido.
    await service.confirm_password_reset(second_token, "contraseña-valida-2")


async def test_signup_clinic_generates_clinic_code_from_name(
    db_session: AsyncSession,
) -> None:
    service, _ = _make_service(db_session)

    await service.signup_clinic(
        ClinicSignupData(
            clinic_name="Clínica Auditiva Vila-real",
            admin_email="codigo@test.local",
            admin_display_name="Test",
            admin_password=_PASSWORD,
        )
    )

    clinic = await SqlAlchemyClinicRepository().get_by_code(
        db_session, "CLINICA-AUDITIVA-VILA-REAL"
    )
    assert clinic is not None
    assert clinic.name == "Clínica Auditiva Vila-real"
