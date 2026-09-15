"""Tests de InvitationService — Fase 12, hito 12.2. Mismo criterio de
no-enumeración que test_onboarding_service.py para
request_password_reset: la respuesta al admin nunca revela si el email
invitado ya tiene cuenta, solo cambia qué email se envía."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.integrations.domain.email_sender import EmailMessage
from app.onboarding.invitation_service import InvitationAcceptData, InvitationService
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository
from tests.factories import ClinicWithUsers, create_user, current_user_from

_PASSWORD = "contraseña-de-doce"


class _RecordingEmailSender:
    """Doble de test de `EmailSender` — nunca contacta un proveedor real,
    solo guarda los mensajes para que el test los inspeccione."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _make_service(session: AsyncSession) -> tuple[InvitationService, _RecordingEmailSender]:
    email_sender = _RecordingEmailSender()
    service = InvitationService(session, email_sender=email_sender)
    return service, email_sender


def _extract_token_from_link(html_body: str) -> str:
    return html_body.split("token=")[1].split('"')[0]


async def test_create_invitation_sends_invite_email_to_new_address(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)

    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "nueva-companera@test.local", Role.AUDIOLOGIST
    )

    assert len(email_sender.sent) == 1
    sent = email_sender.sent[0]
    assert sent.to_email == "nueva-companera@test.local"
    assert "accept-invitation?token=" in sent.html_body


async def test_create_invitation_requires_admin_role(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _make_service(db_session)
    audiologist = current_user_from(clinic_with_users.audiologist)

    with pytest.raises(ForbiddenError):
        await service.create_invitation(
            audiologist, clinic_with_users.clinic.id, "quien-sea@test.local", Role.VIEWER
        )


async def test_create_invitation_rejects_mismatched_clinic_id(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, _ = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)

    with pytest.raises(ForbiddenError):
        await service.create_invitation(
            admin, uuid.uuid4(), "quien-sea@test.local", Role.AUDIOLOGIST
        )


async def test_create_invitation_rejects_admin_role_even_bypassing_the_schema(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """Defensa en profundidad: `InvitationCreateRequest` ya excluye `admin`
    a nivel de esquema (422) — esto cubre cualquier llamador que invoque
    el servicio directamente."""
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)

    with pytest.raises(ConflictError) as exc_info:
        await service.create_invitation(
            admin, clinic_with_users.clinic.id, "aspirante-a-admin@test.local", Role.ADMIN
        )

    assert exc_info.value.field == "role"
    assert email_sender.sent == []


async def test_create_invitation_for_already_registered_email_is_silent_to_the_admin(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    """No-enumeración (RFC §6): ni excepción ni ningún efecto observable
    distinto para el admin — solo cambia el email que recibe el aviso."""
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)

    await service.create_invitation(
        admin, clinic_with_users.clinic.id, clinic_with_users.viewer.email, Role.AUDIOLOGIST
    )

    assert len(email_sender.sent) == 1
    sent = email_sender.sent[0]
    assert sent.to_email == clinic_with_users.viewer.email
    assert "accept-invitation?token=" not in sent.html_body
    assert "ya tiene una cuenta" in sent.html_body


async def test_accept_invitation_creates_active_user_with_proposed_role(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)
    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "compañera@test.local", Role.VIEWER
    )
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)

    await service.accept_invitation(
        InvitationAcceptData(token=raw_token, new_password=_PASSWORD, display_name="Compañera")
    )

    user = await SqlAlchemyUserRepository().get_by_email(db_session, "compañera@test.local")
    assert user is not None
    assert user.is_active is True
    assert user.role == Role.VIEWER
    assert user.clinic_id == clinic_with_users.clinic.id
    assert user.display_name == "Compañera"


async def test_accept_invitation_with_invalid_token_raises_not_found(
    db_session: AsyncSession,
) -> None:
    service, _ = _make_service(db_session)

    with pytest.raises(NotFoundError):
        await service.accept_invitation(
            InvitationAcceptData(
                token="token-inventado-que-no-existe",
                new_password=_PASSWORD,
                display_name="Quien sea",
            )
        )


async def test_accept_invitation_with_already_accepted_token_raises_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)
    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "otra-companera@test.local", Role.AUDIOLOGIST
    )
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)
    await service.accept_invitation(
        InvitationAcceptData(token=raw_token, new_password=_PASSWORD, display_name="Alguien")
    )

    with pytest.raises(ConflictError):
        await service.accept_invitation(
            InvitationAcceptData(
                token=raw_token, new_password="otra-contraseña-x", display_name="Alguien Más"
            )
        )


async def test_accept_invitation_with_email_taken_meanwhile_raises_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)
    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "carrera@test.local", Role.AUDIOLOGIST
    )
    raw_token = _extract_token_from_link(email_sender.sent[0].html_body)
    # El email se registra por otra vía (p. ej. alta de clínica propia)
    # DESPUÉS de emitirse la invitación, antes de aceptarla.
    await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.VIEWER, email="carrera@test.local"
    )

    with pytest.raises(ConflictError) as exc_info:
        await service.accept_invitation(
            InvitationAcceptData(token=raw_token, new_password=_PASSWORD, display_name="Alguien")
        )

    assert exc_info.value.field == "email"


async def test_reinviting_the_same_email_invalidates_the_previous_invitation(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    service, email_sender = _make_service(db_session)
    admin = current_user_from(clinic_with_users.admin)

    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "reinvitada@test.local", Role.VIEWER
    )
    first_token = _extract_token_from_link(email_sender.sent[0].html_body)
    await service.create_invitation(
        admin, clinic_with_users.clinic.id, "reinvitada@test.local", Role.AUDIOLOGIST
    )
    second_token = _extract_token_from_link(email_sender.sent[1].html_body)

    assert first_token != second_token
    with pytest.raises(ConflictError):
        await service.accept_invitation(
            InvitationAcceptData(
                token=first_token, new_password=_PASSWORD, display_name="Reinvitada"
            )
        )

    # El segundo (el último enviado) sigue siendo válido, con el rol de la
    # segunda invitación.
    await service.accept_invitation(
        InvitationAcceptData(token=second_token, new_password=_PASSWORD, display_name="Reinvitada")
    )
    user = await SqlAlchemyUserRepository().get_by_email(db_session, "reinvitada@test.local")
    assert user is not None
    assert user.role == Role.AUDIOLOGIST
