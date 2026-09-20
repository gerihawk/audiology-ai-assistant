"""Servicios de la Fase 14 (panel de gestión de clínicas del operador de
la plataforma):

- `PlatformAdminAuthService.login`: mismo patrón que `app.auth.service.
  AuthService.login` (bcrypt + JWT de vida corta), pero contra
  `platform_operators`, nunca contra `users`. El JWT resultante lleva un
  claim `typ="platform_operator"` que `get_current_platform_operator`
  (app/platform_admin/api/deps.py) exige explícitamente — así un JWT de
  usuario de clínica robado nunca sirve para autenticarse aquí, aunque
  ambos tipos de token compartan `jwt_secret_key`/algoritmo (mismo
  criterio que ya comparten `AuthService`/`RealCurrentUserProvider`: si
  ese secreto se filtra, todo el sistema de auth ya está comprometido por
  igual).
- `PlatformAdminService`: listar todas las clínicas y activar/desactivar
  una — delega en `SqlAlchemyClinicRepository` (módulo `clinics`), sin
  tabla ni entidad propia para esto. Nunca pasa por
  `app.core.authorization` (ninguna de sus funciones `authorize_*`
  conoce este caso de uso: no hay `CurrentUser`/`Role` de por medio).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import Settings, get_settings
from app.core.current_user import JWT_ALGORITHM
from app.core.exceptions import NotFoundError, UnauthenticatedError
from app.platform_admin.infrastructure.repository import SqlAlchemyPlatformOperatorRepository

#: Más corto que `ACCESS_TOKEN_TTL` de `AuthService` (8h): un token de
#: operador de plataforma es de alto privilegio (ve/gestiona TODAS las
#: clínicas), así que su ventana de validez se acota más.
PLATFORM_ACCESS_TOKEN_TTL = timedelta(hours=2)

#: Claim que distingue este token de un JWT normal de `AuthService` — ver
#: docstring del módulo.
PLATFORM_TOKEN_TYPE = "platform_operator"

# Mismo mensaje genérico y mismo mecanismo anti-canal-lateral de tiempo que
# `app.auth.service.AuthService` — ver su docstring para el razonamiento
# completo (nunca se distingue "no existe" de "contraseña incorrecta").
_INVALID_CREDENTIALS_MESSAGE = "Email o contraseña incorrectos."
_DUMMY_PASSWORD_HASH = "$2b$12$reGYj6MH34Vqzv/tteadR.rlnCNHI9BnZUOmuQBXbyFJAhMO8bcni"


class PlatformAdminAuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        operator_repository: SqlAlchemyPlatformOperatorRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._operators = operator_repository or SqlAlchemyPlatformOperatorRepository()

    async def login(self, email: str, password: str) -> str:
        operator = await self._operators.get_by_email(self._session, email)
        password_hash = operator.password_hash if operator is not None else None
        # Siempre se ejecuta, nunca en cortocircuito — ver `_DUMMY_PASSWORD_HASH`.
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"), (password_hash or _DUMMY_PASSWORD_HASH).encode("utf-8")
        )
        if (
            operator is None
            or password_hash is None
            or not operator.is_active
            or not password_matches
        ):
            raise UnauthenticatedError(_INVALID_CREDENTIALS_MESSAGE)

        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(operator.id),
                "typ": PLATFORM_TOKEN_TYPE,
                "iat": now,
                "exp": now + PLATFORM_ACCESS_TOKEN_TTL,
            },
            self._settings.jwt_secret_key,
            algorithm=JWT_ALGORITHM,
        )


class PlatformAdminService:
    """Operaciones de negocio del panel — sin `CurrentUser` como
    parámetro: quien llama ya pasó por `get_current_platform_operator`,
    que no produce un `CurrentUser` (no tiene sentido para una identidad
    sin clínica), así que estos métodos no reciben ninguna identidad
    explícita, igual que un endpoint de cron protegido por secreto."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
    ) -> None:
        self._session = session
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()

    async def list_clinics(self) -> list[Clinic]:
        return await self._clinics.list_all(self._session)

    async def set_clinic_active(self, clinic_id: uuid.UUID, *, is_active: bool) -> Clinic:
        clinic = await self._clinics.set_active(self._session, clinic_id, is_active=is_active)
        if clinic is None:
            raise NotFoundError("La clínica no existe.")
        await self._session.commit()
        return clinic
