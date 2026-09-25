"""Endpoints POST /auth/login (Fase 9, hito 9.1) y POST /auth/logout
(hallazgo D1 del red team).

`/login` sin autorización previa (`Depends(get_current_user)`): es el
propio punto de entrada de autenticación, tiene que ser accesible sin
sesión. `/logout` sí la exige: revoca los tokens del usuario autenticado.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.api.schemas import LoginRequest, LoginResponse
from app.auth.service import AuthService
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_auth_service, get_current_user
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def logout(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    request_id: str = Depends(get_request_id),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    await service.logout(current_user, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
