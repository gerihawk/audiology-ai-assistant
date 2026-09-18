"""OnboardingService (Fase 12, hito 12.1): alta pública de una clínica
nueva, verificación de email y recuperación de contraseña.

Ver docs/fase-12-rfc.md. Tres flujos, todos SIN `CurrentUser` (superficie
pública, a diferencia del resto de servicios del proyecto — mismo criterio
que `AuthService.login`, el propio punto de entrada de autenticación):

1. `signup_clinic`: crea `Clinic` + primer `User` (rol `admin`,
   `is_active=False`) y envía el email de verificación.
2. `verify_email`: activa el usuario si el token es válido.
3. `request_password_reset`/`confirm_password_reset`: emite y consume un
   token de reseteo — nunca reutiliza el de verificación (propósitos
   distintos, ver `AccountTokenPurpose`).

La Fase 12, hito 12.2 (invitar a un compañero de la misma clínica) es un
servicio/endpoint aparte — no se adelanta aquí.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.integrations.domain.email_sender import EmailMessage, EmailSender
from app.integrations.domain.turnstile_verifier import TurnstileVerifier
from app.integrations.factory import build_email_sender, build_turnstile_verifier
from app.onboarding.domain.clinic_code import slugify_clinic_name
from app.onboarding.domain.disposable_email_domains import is_disposable_email_domain
from app.onboarding.domain.entities import AccountToken, AccountTokenPurpose
from app.onboarding.domain.normalization import (
    normalize_email,
    normalize_required_free_text,
    validate_password_length,
)
from app.onboarding.infrastructure.repository import SqlAlchemyAccountTokenRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository

#: `ClinicORM.code` es `String(32)` — ver `slugify_clinic_name`
#: (`_MAX_BASE_LENGTH=27`) para el resto del presupuesto de caracteres.
_CLINIC_CODE_SUFFIX_LENGTH = 4
_CLINIC_CODE_MAX_ATTEMPTS = 5


@dataclass(slots=True)
class ClinicSignupData:
    clinic_name: str
    admin_email: str
    admin_display_name: str
    admin_password: str
    #: Fase 12, hito 12.4 ampliado (2026-09-18) — ver docstring de
    #: `OnboardingService.signup_clinic`. Con default para no romper
    #: llamadores/tests existentes anteriores a esta fase; en la práctica
    #: `POST /clinics/signup` siempre lo envía (`ClinicSignupRequest.turnstile_token`
    #: es obligatorio en el esquema Pydantic).
    turnstile_token: str = ""
    #: IP real del visitante (ver app/core/rate_limit.py::client_ip_key) —
    #: opcional, solo mejora la puntuación de Cloudflare, nunca bloqueante.
    remote_ip: str | None = None


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    """Mismo algoritmo que `app.seed`/`AuthService` — bcrypt directo, sin passlib."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class OnboardingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
        account_token_repository: SqlAlchemyAccountTokenRepository | None = None,
        email_sender: EmailSender | None = None,
        turnstile_verifier: TurnstileVerifier | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._users = user_repository or SqlAlchemyUserRepository()
        self._tokens = account_token_repository or SqlAlchemyAccountTokenRepository()
        self._email_sender = email_sender or build_email_sender(self._settings)
        self._turnstile_verifier = turnstile_verifier or build_turnstile_verifier(self._settings)

    async def signup_clinic(self, data: ClinicSignupData) -> None:
        """A diferencia de `request_password_reset` (siempre silencioso, ver
        más abajo), un email ya registrado SÍ se comunica explícitamente
        (`ConflictError`, 409): en un formulario público de alta — a
        diferencia del login — quien envía el formulario ya sabe que ese
        email existe (lo acaba de escribir él mismo) y el riesgo real de
        enumeración es bajo frente al coste de UX de no poder decirle
        "ese email ya tiene cuenta, inicia sesión en su lugar".

        Anti-abuso (Fase 12, hito 12.4 ampliado, decisión del 2026-09-18 —
        ver docs/fase-12-rfc.md §6): dos capas independientes, además del
        rate limiting de 5/minute ya existente en el router (ver
        app/onboarding/api/router.py). Se comprueban en este orden por
        coste creciente — local y gratis primero, llamada de red después
        — para no gastar una verificación contra Cloudflare en un email ya
        descartable localmente:

        1. Dominio de email desechable (`is_disposable_email_domain`):
           reutiliza el mismo `ConflictError(field="admin_email")` que el
           email duplicado — misma superficie de error ya manejada por el
           frontend para este campo.
        2. Turnstile (`self._turnstile_verifier.verify`): filtra tráfico
           de script/bot genérico. Un fallo aquí no es específico de
           ningún campo del formulario, así que se usa `ForbiddenError`
           (403) en vez de `ConflictError`.
        """
        admin_email = normalize_email(data.admin_email)
        admin_display_name = normalize_required_free_text(
            data.admin_display_name, field_name="admin_display_name"
        )
        clinic_name = normalize_required_free_text(data.clinic_name, field_name="clinic_name")
        validate_password_length(data.admin_password)

        if is_disposable_email_domain(admin_email):
            raise ConflictError(
                "No se admiten direcciones de email de proveedores desechables/temporales.",
                field="admin_email",
            )

        turnstile_ok = await self._turnstile_verifier.verify(
            data.turnstile_token, remote_ip=data.remote_ip
        )
        if not turnstile_ok:
            raise ForbiddenError(
                "No hemos podido verificar que la solicitud proviene de una persona real. "
                "Vuelve a intentarlo."
            )

        existing_user = await self._users.get_by_email(self._session, admin_email)
        if existing_user is not None:
            raise ConflictError("Ya existe una cuenta con ese email.", field="admin_email")

        now = datetime.now(UTC)
        clinic = Clinic(
            id=uuid.uuid4(),
            name=clinic_name,
            code=await self._generate_unique_clinic_code(clinic_name),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        admin = User(
            id=uuid.uuid4(),
            clinic_id=clinic.id,
            email=admin_email,
            display_name=admin_display_name,
            role=Role.ADMIN,
            # Inactivo hasta verificar el email — `FakeCurrentUserProvider`/
            # `RealCurrentUserProvider` ya rechazan cualquier usuario
            # inactivo (`get_active_by_id`), así que no hace falta ningún
            # guardarraíl adicional para impedir el login antes de verificar.
            is_active=False,
            created_at=now,
            updated_at=now,
            password_hash=_hash_password(data.admin_password),
        )

        await self._clinics.add(self._session, clinic)
        await self._users.add(self._session, admin)
        await self._session.commit()

        await self._issue_and_send_token(
            admin,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            ttl=timedelta(hours=self._settings.email_verification_token_ttl_hours),
            link_path="verify-email",
            subject="Confirma tu email — Audiology AI Assistant",
            build_html=lambda link: (
                f"<p>Hola {admin_display_name},</p>"
                f"<p>Confirma tu email para activar la cuenta de "
                f"<strong>{clinic_name}</strong>:</p>"
                f'<p><a href="{link}">{link}</a></p>'
                f"<p>Este enlace caduca en "
                f"{self._settings.email_verification_token_ttl_hours} horas.</p>"
            ),
            build_text=lambda link: (
                f"Hola {admin_display_name}, confirma tu email para activar la cuenta de "
                f"{clinic_name}: {link} "
                f"(caduca en {self._settings.email_verification_token_ttl_hours} horas)"
            ),
        )

    async def verify_email(self, raw_token: str) -> None:
        token = await self._require_usable_token(raw_token, AccountTokenPurpose.EMAIL_VERIFICATION)
        # `get_by_id` (no `get_active_by_id`): el usuario a activar está,
        # por definición, todavía inactivo.
        user = await self._users.get_by_id(self._session, token.user_id)
        if user is None:
            raise NotFoundError("El usuario asociado a este enlace ya no existe.")
        await self._users.set_active(self._session, user.id, is_active=True)
        await self._tokens.mark_used(self._session, token.id)
        await self._session.commit()

    async def request_password_reset(self, email: str) -> None:
        """Siempre silencioso, exista o no la cuenta — mismo criterio de
        no-enumeración que `AuthService.login` (aquí no hace falta además
        igualar el tiempo de respuesta: no hay ninguna operación lenta
        tipo bcrypt en la rama "no existe", así que no hay canal lateral
        de timing que cerrar)."""
        normalized_email = normalize_email(email)
        user = await self._users.get_by_email(self._session, normalized_email)
        if user is None or not user.is_active:
            return

        await self._issue_and_send_token(
            user,
            purpose=AccountTokenPurpose.PASSWORD_RESET,
            ttl=timedelta(hours=self._settings.password_reset_token_ttl_hours),
            link_path="reset-password",
            subject="Recupera tu contraseña — Audiology AI Assistant",
            build_html=lambda link: (
                f"<p>Hola {user.display_name},</p>"
                f"<p>Hemos recibido una petición para restablecer tu contraseña. "
                f"Si no has sido tú, ignora este email.</p>"
                f'<p><a href="{link}">{link}</a></p>'
                f"<p>Este enlace caduca en "
                f"{self._settings.password_reset_token_ttl_hours} horas.</p>"
            ),
            build_text=lambda link: (
                f"Hola {user.display_name}, para restablecer tu contraseña visita: {link} "
                f"(caduca en {self._settings.password_reset_token_ttl_hours} horas). "
                "Si no has sido tú, ignora este email."
            ),
        )

    async def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        validate_password_length(new_password)

        token = await self._require_usable_token(raw_token, AccountTokenPurpose.PASSWORD_RESET)
        user = await self._users.get_by_id(self._session, token.user_id)
        if user is None:
            raise NotFoundError("El usuario asociado a este enlace ya no existe.")

        await self._users.set_password_hash(self._session, user.id, _hash_password(new_password))
        await self._tokens.mark_used(self._session, token.id)
        # Cualquier otro enlace de reseteo pendiente para este usuario deja
        # de ser válido tras un cambio de contraseña efectivo.
        await self._tokens.invalidate_pending(
            self._session, user.id, AccountTokenPurpose.PASSWORD_RESET
        )
        await self._session.commit()

    async def _require_usable_token(
        self, raw_token: str, purpose: AccountTokenPurpose
    ) -> AccountToken:
        token = await self._tokens.get_by_hash(self._session, _hash_token(raw_token), purpose)
        if token is None:
            raise NotFoundError("Enlace no válido.")
        if not token.is_usable:
            raise ConflictError("Este enlace ya se ha usado o ha caducado.")
        return token

    async def _issue_and_send_token(
        self,
        user: User,
        *,
        purpose: AccountTokenPurpose,
        ttl: timedelta,
        link_path: str,
        subject: str,
        build_html,
        build_text,
    ) -> None:
        # Cualquier token pendiente anterior del mismo propósito deja de
        # servir: solo el último enlace enviado por email es válido (p.
        # ej. si el usuario pide reenviar la verificación dos veces).
        await self._tokens.invalidate_pending(self._session, user.id, purpose)

        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        await self._tokens.add(
            self._session,
            AccountToken(
                id=uuid.uuid4(),
                user_id=user.id,
                purpose=purpose,
                token_hash=_hash_token(raw_token),
                expires_at=now + ttl,
                used_at=None,
                created_at=now,
            ),
        )
        await self._session.commit()

        link = f"{self._settings.frontend_base_url.rstrip('/')}/{link_path}?token={raw_token}"
        await self._email_sender.send(
            EmailMessage(
                to_email=user.email,
                to_name=user.display_name,
                subject=subject,
                html_body=build_html(link),
                text_body=build_text(link),
            )
        )

    async def _generate_unique_clinic_code(self, clinic_name: str) -> str:
        base = slugify_clinic_name(clinic_name)
        existing = await self._clinics.get_by_code(self._session, base)
        if existing is None:
            return base
        for _ in range(_CLINIC_CODE_MAX_ATTEMPTS):
            candidate = f"{base}-{secrets.token_hex(_CLINIC_CODE_SUFFIX_LENGTH // 2)}"
            if await self._clinics.get_by_code(self._session, candidate) is None:
                return candidate
        # Extremadamente improbable (colisión repetida de un sufijo
        # aleatorio de 16 bits) — se documenta en vez de reintentar en
        # silencio indefinidamente, mismo criterio que el resto del
        # proyecto ante un caso límite no resuelto automáticamente.
        raise ConflictError(
            "No se ha podido generar un código de clínica único. Inténtalo de nuevo."
        )
