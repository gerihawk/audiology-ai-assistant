"""GET /dev/users — solo desarrollo.

No sustituye a un login: permite poblar un selector de "usuario activo"
en el frontend mientras no exista autenticación real. Este router no se
registra en absoluto cuando ENVIRONMENT=production (ver app.api.router).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DevUserResponse
from app.core.db import get_db_session
from app.users.infrastructure.repository import SqlAlchemyUserRepository

router = APIRouter(prefix="/dev", tags=["dev-tools"])


@router.get("/users", response_model=list[DevUserResponse])
async def list_dev_users(
    session: AsyncSession = Depends(get_db_session),
) -> list[DevUserResponse]:
    users = await SqlAlchemyUserRepository().list_all(session)
    return [DevUserResponse.model_validate(user) for user in users]
