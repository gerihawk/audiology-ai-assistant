"""Esquemas Pydantic de la API de la Fase 14 (panel de gestión de
clínicas del operador de la plataforma)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.clinics.domain.entities import Clinic
from app.platform_admin.domain.entities import PlatformOperator


class PlatformLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class PlatformLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PlatformOperatorResponse(BaseModel):
    """Respuesta de `GET /platform/me` — equivalente de `PlatformOperator`
    para `GET /api/v1/me` (`CurrentUser`), usada por el frontend para
    validar un token persistido en un refresh de página (ver
    `PlatformAuthContext.tsx`). Deliberadamente sin `password_hash`."""

    id: uuid.UUID
    email: str
    display_name: str

    @classmethod
    def from_domain(cls, operator: PlatformOperator) -> PlatformOperatorResponse:
        return cls(id=operator.id, email=operator.email, display_name=operator.display_name)


class PlatformClinicResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    # Slug crudo (ver app/billing/domain/plans.py) y estado crudo de
    # Stripe — sin traducir a etiqueta comercial ni normalizar: por ahora
    # el propio Gerard decidió que mostrar el valor tal cual es
    # suficiente para este panel (Fase 14).
    plan: str | None
    subscription_status: str | None
    sessions_used_this_period: int
    current_period_started_at: datetime | None
    created_at: datetime

    @classmethod
    def from_domain(cls, clinic: Clinic) -> PlatformClinicResponse:
        return cls(
            id=clinic.id,
            name=clinic.name,
            code=clinic.code,
            is_active=clinic.is_active,
            plan=clinic.plan,
            subscription_status=clinic.subscription_status,
            sessions_used_this_period=clinic.sessions_used_this_period,
            current_period_started_at=clinic.current_period_started_at,
            created_at=clinic.created_at,
        )


class PlatformClinicListResponse(BaseModel):
    items: list[PlatformClinicResponse]


class PlatformClinicUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool
