"""Dependencias FastAPI de la Fase 14 — completamente aparte de
`app/core/deps.py::get_current_user`: `get_current_platform_operator`
nunca produce un `CurrentUser` ni pasa por `CurrentUserProvider`/
`FakeCurrentUserProvider`/`RealCurrentUserProvider`. Ver docstring de
`app/platform_admin/service.py` para el razonamiento completo.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.current_user import JWT_ALGORITHM
from app.core.db import get_db_session
from app.core.exceptions import UnauthenticatedError
from app.platform_admin.domain.entities import PlatformOperator
from app.platform_admin.infrastructure.repository import SqlAlchemyPlatformOperatorRepository
from app.platform_admin.service import (
    PLATFORM_TOKEN_TYPE,
    PlatformAdminAuthService,
    PlatformAdminService,
)


async def get_platform_admin_auth_service(
    session: AsyncSession = Depends(get_db_session),
) -> PlatformAdminAuthService:
    return PlatformAdminAuthService(session)


async def get_platform_admin_service(
    session: AsyncSession = Depends(get_db_session),
) -> PlatformAdminService:
    return PlatformAdminService(session)


async def get_current_platform_operator(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> PlatformOperator:
    """Decodifica y valida un JWT Bearer firmado por
    `PlatformAdminAuthService.login`. Exige explícitamente
    `payload["typ"] == "platform_operator"`: sin esta comprobación, un JWT
    de usuario normal de clínica (firmado por `AuthService`, sin claim
    `typ`) podría en teoría autenticarse aquí si su `sub` (el id del
    usuario) coincidiera por azar con un id de `platform_operators` — con
    UUIDs aleatorios de 122 bits la probabilidad es nula, pero el claim
    `typ` lo hace además IMPOSIBLE por construcción, no solo improbable."""
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise UnauthenticatedError("Falta la cabecera Authorization: Bearer <token>.")
    token = header.removeprefix("Bearer ")

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError("El token ha expirado.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("Token inválido.") from exc

    if payload.get("typ") != PLATFORM_TOKEN_TYPE:
        raise UnauthenticatedError("Token inválido.")

    try:
        operator_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthenticatedError("Token inválido.") from exc

    operator = await SqlAlchemyPlatformOperatorRepository().get_active_by_id(session, operator_id)
    if operator is None:
        raise UnauthenticatedError("Operador no encontrado o inactivo.")
    return operator
