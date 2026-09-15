"""Endpoint POST /auth/login — Fase 9, hito 9.1.

Sin autorización previa (`Depends(get_current_user)`): es el propio punto
de entrada de autenticación, tiene que ser accesible sin sesión.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.auth.api.schemas import LoginRequest, LoginResponse
from app.auth.service import AuthService
from app.core.deps import get_auth_service
from app.core.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
# Límite propio (5/minute), más estricto que el general de la app
# (120/minute — ver app/core/rate_limit.py): frena fuerza bruta de
# contraseñas. `override_defaults=True` (por defecto en `limiter.limit`)
# hace que este límite sustituya, no se sume, al general en esta ruta.
@limiter.limit("5/minute")
async def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    token = await service.login(payload.email, payload.password)
    return LoginResponse(access_token=token)
