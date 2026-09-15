"""CurrentUser / CurrentUserProvider.

Puerto que resuelve "quién hace esta petición". Dos implementaciones:
`FakeCurrentUserProvider` (herramienta de desarrollo, X-Dev-User-Id) y
`RealCurrentUserProvider` (JWT Bearer, Fase 9, hito 9.1) — cuál se usa lo
decide `settings.auth_mode` en `core/deps.py::get_current_user_provider()`.
Ver docs/privacy-and-security.md §12.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import jwt
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository

DEV_USER_HEADER = "X-Dev-User-Id"

# Compartido con `AuthService` (app/auth/service.py), que firma el JWT que
# este módulo verifica — misma clave y algoritmo en ambos extremos.
JWT_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    clinic_id: uuid.UUID
    email: str
    display_name: str
    role: Role


class CurrentUserProvider(Protocol):
    async def get_current_user(self, request: Request, session: AsyncSession) -> CurrentUser: ...


class FakeCurrentUserProvider:
    """Resuelve un usuario ficticio de desarrollo. Nunca usar en producción.

    No verifica contraseña ni ningún factor real: solo confirma que el id
    recibido corresponde a un usuario existente y activo en la base de
    datos (nunca confía ciegamente en lo enviado por el cliente).
    """

    def __init__(
        self,
        settings: Settings,
        user_repository: SqlAlchemyUserRepository | None = None,
    ) -> None:
        if settings.is_production or settings.is_staging:
            raise RuntimeError(
                "FakeCurrentUserProvider no puede utilizarse con "
                "ENVIRONMENT=production ni ENVIRONMENT=staging."
            )
        self._settings = settings
        self._user_repository = user_repository or SqlAlchemyUserRepository()

    async def get_current_user(self, request: Request, session: AsyncSession) -> CurrentUser:
        raw_id = request.headers.get(DEV_USER_HEADER) or self._settings.dev_default_user_id
        if not raw_id:
            raise UnauthenticatedError(
                f"Falta la cabecera {DEV_USER_HEADER} o DEV_DEFAULT_USER_ID en la configuración."
            )
        try:
            user_id = uuid.UUID(raw_id)
        except ValueError as exc:
            raise UnauthenticatedError(f"{DEV_USER_HEADER} no es un UUID válido.") from exc

        user = await self._user_repository.get_active_by_id(session, user_id)
        if user is None:
            raise UnauthenticatedError("Usuario de desarrollo no encontrado o inactivo.")

        return CurrentUser(
            id=user.id,
            clinic_id=user.clinic_id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )


class RealCurrentUserProvider:
    """Decodifica y valida un JWT Bearer del header `Authorization`
    (`Bearer <token>`), firmado por `AuthService.login` (Fase 9, hito
    9.1). Mismo criterio de validación de usuario que
    `FakeCurrentUserProvider`: debe existir y estar activo — el JWT solo
    prueba quién lo obtuvo, no que la cuenta siga siendo válida ahora."""

    def __init__(
        self,
        settings: Settings,
        user_repository: SqlAlchemyUserRepository | None = None,
    ) -> None:
        self._settings = settings
        self._user_repository = user_repository or SqlAlchemyUserRepository()

    async def get_current_user(self, request: Request, session: AsyncSession) -> CurrentUser:
        header = request.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            raise UnauthenticatedError("Falta la cabecera Authorization: Bearer <token>.")
        token = header.removeprefix("Bearer ")

        try:
            payload = jwt.decode(token, self._settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise UnauthenticatedError("El token ha expirado.") from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthenticatedError("Token inválido.") from exc

        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise UnauthenticatedError("Token inválido.") from exc

        user = await self._user_repository.get_active_by_id(session, user_id)
        if user is None:
            raise UnauthenticatedError("Usuario no encontrado o inactivo.")

        return CurrentUser(
            id=user.id,
            clinic_id=user.clinic_id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )
