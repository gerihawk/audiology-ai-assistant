"""Endpoint POST /auth/login — Fase 9, hito 9.1.

Sin autorización previa (`Depends(get_current_user)`): es el propio punto
de entrada de autenticación, tiene que ser accesible sin sesión.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.api.schemas import LoginRequest, LoginResponse
from app.auth.service import AuthService
from app.core.deps import get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    token = await service.login(payload.email, payload.password)
    return LoginResponse(access_token=token)
