"""Endpoints de liveness (/health) y readiness (/ready).

Sin dependencias de dominio: estos endpoints no pertenecen a ningún módulo
clínico y no deben acumular lógica de negocio.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.rate_limit import limiter

router = APIRouter(tags=["health"])


@router.get("/health")
# Exento del límite general de 120/minute (Fase 10.5): Railway lo usa para
# comprobar que el proceso sigue vivo y no debe verse afectado por el
# tráfico de la app.
@limiter.exempt
async def health() -> dict[str, str]:
    """Liveness: el proceso está arriba, sin comprobar dependencias externas."""
    return {"status": "ok"}


@router.get("/ready")
@limiter.exempt
async def ready(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """Readiness: comprueba conectividad real con PostgreSQL."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unreachable"},
        )
    return JSONResponse(content={"status": "ok", "database": "connected"})
