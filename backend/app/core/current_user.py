"""CurrentUser / CurrentUserProvider.

Puerto que resuelve "quién hace esta petición". Sin autenticación real
todavía: la única implementación es FakeCurrentUserProvider, una
herramienta de desarrollo (ver docs/privacy-and-security.md §12).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository

DEV_USER_HEADER = "X-Dev-User-Id"


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
        if settings.is_production:
            raise RuntimeError(
                "FakeCurrentUserProvider no puede utilizarse con ENVIRONMENT=production."
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
