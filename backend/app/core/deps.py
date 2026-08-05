"""Dependencias FastAPI: sesión de BD, usuario actual, servicios."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser, CurrentUserProvider, FakeCurrentUserProvider
from app.core.db import get_db_session
from app.patients.service import PatientService

__all__ = [
    "get_db_session",
    "get_request_id",
    "get_current_user_provider",
    "get_current_user",
    "get_patient_service",
]


@lru_cache
def get_current_user_provider() -> CurrentUserProvider:
    """Se cachea: la validación de producción de FakeCurrentUserProvider
    ocurre una única vez, en la primera invocación (idealmente en el
    arranque de la app, ver app.main lifespan)."""
    return FakeCurrentUserProvider(get_settings())


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    provider: CurrentUserProvider = Depends(get_current_user_provider),
) -> CurrentUser:
    return await provider.get_current_user(request, session)


async def get_patient_service(
    session: AsyncSession = Depends(get_db_session),
) -> PatientService:
    return PatientService(session)
