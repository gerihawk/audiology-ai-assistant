"""InvitationService (Fase 12, hito 12.2): invitar a un compañero de la
misma clínica.

Ver docs/fase-12-rfc.md §4.2/§5/§6/§7. Servicio deliberadamente aparte de
`OnboardingService` (ver su docstring, que ya anunciaba esta separación)
aunque comparta módulo `onboarding` y el mismo puerto `EmailSender`: dos
flujos de negocio distintos (alta de una clínica nueva vs. invitar a un
compañero dentro de una clínica ya existente).

Dos operaciones:
1. `create_invitation`: solo `admin`, y solo sobre su propia clínica (ver
   `authorize_invitation_action`). No-enumeración (RFC §6): la respuesta
   al admin es siempre la misma exista o no ya una cuenta con ese email —
   la rama distinta (invitación real vs. aviso de "ya tienes cuenta") solo
   es visible en el email enviado, nunca en la respuesta HTTP ni en
   excepciones — mismo criterio que
   `OnboardingService.request_password_reset`.
2. `accept_invitation`: sin autenticación previa (token de un solo uso),
   fija contraseña y nombre visible, crea el `User` con el rol propuesto,
   `is_active=True` desde el principio (a diferencia del alta de clínica:
   quien acepta ya demostró control del email al recibir el enlace, no
   hace falta una verificación adicional).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.authorization import InvitationAction, authorize_invitation_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.integrations.domain.email_sender import EmailMessage, EmailSender
from app.integrations.factory import build_email_sender
from app.onboarding.domain.entities import INVITABLE_ROLES, Invitation
from app.onboarding.domain.normalization import (
    normalize_email,
    normalize_required_free_text,
    validate_password_length,
)
from app.onboarding.infrastructure.repository import SqlAlchemyInvitationRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository

_DISPLAY_NAME_FIELD = "display_name"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    """Mismo algoritmo que `OnboardingService`/`app.seed`/`AuthService` —
    bcrypt directo, sin passlib."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@dataclass(slots=True)
class InvitationAcceptData:
    token: str
    new_password: str
    #: El RFC ("fija contraseña, crea User...") no menciona este campo,
    #: pero `User.display_name` es NOT NULL y en el momento de invitar no
    #: se conoce el nombre de quien acepta — se pide aquí, mismo criterio
    #: que `admin_display_name` en `ClinicSignupData`.
    display_name: str


class InvitationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
        invitation_repository: SqlAlchemyInvitationRepository | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._users = user_repository or SqlAlchemyUserRepository()
        self._invitations = invitation_repository or SqlAlchemyInvitationRepository()
        self._email_sender = email_sender or build_email_sender(self._settings)

    async def create_invitation(
        self, current_user: CurrentUser, clinic_id: uuid.UUID, email: str, role: Role
    ) -> None:
        authorize_invitation_action(current_user, InvitationAction.CREATE, clinic_id=clinic_id)
        if role not in INVITABLE_ROLES:
            # Defensa en profundidad: `InvitationCreateRequest` ya restringe
            # `role` a un `Literal` que excluye `admin` y rechaza con 422
            # cualquier otro valor antes de llegar aquí — esto solo cubre a
            # cualquier llamador que no pase por la API HTTP.
            raise ConflictError("El rol propuesto no es invitable.", field="role")

        normalized_email = normalize_email(email)

        # Reinvitar (mismo email, misma clínica) invalida el enlace
        # anterior — el admin ya sabe que está reinvitando, así que esto no
        # es una operación sensible a la no-enumeración de más abajo.
        await self._invitations.invalidate_pending_for_email(
            self._session, clinic_id, normalized_email
        )

        # No-enumeración (RFC §6): `email` es global (`users.email` es
        # único en toda la aplicación, no por clínica, ver
        # app/users/infrastructure/orm.py) — si YA existe un `User` con
        # este email (en esta clínica o en cualquier otra, activo o no:
        # `accept_invitation`/`signup_clinic` tratan cualquier fila
        # existente como colisión), la única diferencia observable está en
        # qué email se envía, nunca en la respuesta HTTP al admin.
        existing_user = await self._users.get_by_email(self._session, normalized_email)
        if existing_user is not None:
            await self._session.commit()
            await self._send_already_registered_notice(normalized_email)
            return

        clinic = await self._clinics.get_by_id(self._session, clinic_id)
        clinic_name = clinic.name if clinic is not None else ""

        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        ttl = timedelta(days=self._settings.invitation_token_ttl_days)
        await self._invitations.add(
            self._session,
            Invitation(
                id=uuid.uuid4(),
                clinic_id=clinic_id,
                email=normalized_email,
                role=role,
                token_hash=_hash_token(raw_token),
                expires_at=now + ttl,
                accepted_at=None,
                created_by=current_user.id,
                created_at=now,
            ),
        )
        await self._session.commit()

        link = f"{self._settings.frontend_base_url.rstrip('/')}/accept-invitation?token={raw_token}"
        ttl_days = self._settings.invitation_token_ttl_days
        await self._email_sender.send(
            EmailMessage(
                to_email=normalized_email,
                # Nombre real desconocido hasta que acepte la invitación.
                to_name=normalized_email,
                subject=f"Invitación a {clinic_name} — Audiology AI Assistant",
                html_body=(
                    f"<p>Te han invitado a unirte a <strong>{clinic_name}</strong> en "
                    "Audiology AI Assistant.</p>"
                    f'<p><a href="{link}">{link}</a></p>'
                    f"<p>Este enlace caduca en {ttl_days} días.</p>"
                ),
                text_body=(
                    f"Te han invitado a unirte a {clinic_name} en Audiology AI Assistant: "
                    f"{link} (caduca en {ttl_days} días)"
                ),
            )
        )

    async def _send_already_registered_notice(self, email: str) -> None:
        """Rama silenciosa de la no-enumeración: quien recibe este email ya
        tiene cuenta — se le informa a ÉL, nunca al admin que envió la
        invitación (que recibe la misma respuesta HTTP en cualquier
        caso)."""
        await self._email_sender.send(
            EmailMessage(
                to_email=email,
                to_name=email,
                subject="Ya tienes una cuenta — Audiology AI Assistant",
                html_body=(
                    "<p>Alguien ha intentado invitarte a una clínica en Audiology AI "
                    "Assistant, pero este email ya tiene una cuenta.</p>"
                    "<p>Si no reconoces esta invitación, puedes ignorar este mensaje. Si "
                    "esperabas unirte a una nueva clínica con este email, contacta con "
                    "quien te haya invitado.</p>"
                ),
                text_body=(
                    "Alguien ha intentado invitarte a una clínica en Audiology AI "
                    "Assistant, pero este email ya tiene una cuenta. Si no reconoces esta "
                    "invitación, puedes ignorar este mensaje."
                ),
            )
        )

    async def accept_invitation(self, data: InvitationAcceptData) -> None:
        validate_password_length(data.new_password)
        display_name = normalize_required_free_text(
            data.display_name, field_name=_DISPLAY_NAME_FIELD
        )

        invitation = await self._invitations.get_by_hash(self._session, _hash_token(data.token))
        if invitation is None:
            raise NotFoundError("Enlace no válido.")
        if not invitation.is_usable:
            raise ConflictError("Este enlace ya se ha usado o ha caducado.")

        # El email pudo registrarse por otra vía DESPUÉS de emitirse la
        # invitación (p. ej. alta de clínica propia con el mismo email) —
        # igual que `OnboardingService.signup_clinic`, quien acepta ya
        # conoce su propio email, así que comunicar el conflicto aquí no es
        # una fuga de enumeración (a diferencia de `create_invitation`).
        existing_user = await self._users.get_by_email(self._session, invitation.email)
        if existing_user is not None:
            raise ConflictError("Ya existe una cuenta con ese email.", field="email")

        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4(),
            clinic_id=invitation.clinic_id,
            email=invitation.email,
            display_name=display_name,
            role=invitation.role,
            is_active=True,
            created_at=now,
            updated_at=now,
            password_hash=_hash_password(data.new_password),
        )
        await self._users.add(self._session, user)
        await self._invitations.mark_accepted(self._session, invitation.id)
        await self._session.commit()
