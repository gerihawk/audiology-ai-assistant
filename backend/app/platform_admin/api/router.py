"""Endpoints de la Fase 14 (panel de gestión de clínicas del operador de
la plataforma), bajo el prefijo `/platform` — deliberadamente fuera de
`/clinics`/`/auth` (los prefijos de los usuarios normales de clínica), para
que quede claro a simple vista que esta zona de la API tiene su propio
mecanismo de identidad. Ver docstring de `app/platform_admin/service.py`.

`POST /platform/auth/login`: público, mismo límite de 5/minute que
`POST /auth/login` (misma razón: frenar fuerza bruta de contraseñas).

`GET /platform/clinics` / `PATCH /platform/clinics/{clinic_id}`:
protegidos por `get_current_platform_operator` — nunca por
`get_current_user`/`authorize_*`, que no tienen ningún concepto aplicable
aquí (no hay clínica ni rol de por medio).

`GET /platform/me`: equivalente de `GET /api/v1/me` para este mundo — el
frontend lo usa para validar un token persistido en `sessionStorage` tras
un refresh de página, mismo patrón que `AuthContext.tsx` con `CurrentUser`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.core.rate_limit import limiter
from app.platform_admin.api.deps import (
    get_current_platform_operator,
    get_platform_admin_auth_service,
    get_platform_admin_service,
)
from app.platform_admin.api.schemas import (
    PlatformClinicListResponse,
    PlatformClinicResponse,
    PlatformClinicUpdateRequest,
    PlatformLoginRequest,
    PlatformLoginResponse,
    PlatformOperatorResponse,
)
from app.platform_admin.domain.entities import PlatformOperator
from app.platform_admin.service import PlatformAdminAuthService, PlatformAdminService

router = APIRouter(prefix="/platform", tags=["platform-admin"])


@router.post("/auth/login", response_model=PlatformLoginResponse)
@limiter.limit("5/minute")
async def platform_login(
    payload: PlatformLoginRequest,
    request: Request,
    service: PlatformAdminAuthService = Depends(get_platform_admin_auth_service),
) -> PlatformLoginResponse:
    token = await service.login(payload.email, payload.password)
    return PlatformLoginResponse(access_token=token)


@router.get("/me", response_model=PlatformOperatorResponse)
async def get_platform_me(
    operator: PlatformOperator = Depends(get_current_platform_operator),
) -> PlatformOperatorResponse:
    return PlatformOperatorResponse.from_domain(operator)


@router.get("/clinics", response_model=PlatformClinicListResponse)
async def list_clinics(
    _operator: PlatformOperator = Depends(get_current_platform_operator),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> PlatformClinicListResponse:
    clinics = await service.list_clinics()
    return PlatformClinicListResponse(
        items=[PlatformClinicResponse.from_domain(clinic) for clinic in clinics]
    )


@router.patch("/clinics/{clinic_id}", response_model=PlatformClinicResponse)
async def update_clinic(
    clinic_id: uuid.UUID,
    payload: PlatformClinicUpdateRequest,
    _operator: PlatformOperator = Depends(get_current_platform_operator),
    service: PlatformAdminService = Depends(get_platform_admin_service),
) -> PlatformClinicResponse:
    clinic = await service.set_clinic_active(clinic_id, is_active=payload.is_active)
    return PlatformClinicResponse.from_domain(clinic)
