"""Esquemas Pydantic de la API de la Fase 14 (panel de gestión de
clínicas del operador de la plataforma)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

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
    # Solo tiene sentido para el nivel Cadena/Empresa (ampliación
    # 2026-09-21) — `None` en cualquier otro nivel, o en Cadena/Empresa
    # mientras esa clínica no tenga un tope negociado todavía.
    negotiated_included_sessions: int | None
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
            negotiated_included_sessions=clinic.negotiated_included_sessions,
            created_at=clinic.created_at,
        )


class PlatformClinicListResponse(BaseModel):
    items: list[PlatformClinicResponse]


class PlatformClinicUpdateRequest(BaseModel):
    """Actualización parcial (PATCH real): cada campo se aplica solo si
    se incluye explícitamente en el payload — se distingue "no incluido"
    de "incluido como null" vía `model_fields_set` (ver
    `app.platform_admin.api.router.update_clinic`), así que SÍ es
    posible volver `negotiated_included_sessions` a `null` enviándolo
    explícitamente (única vía del panel para revertir un tope negociado
    mal introducido). Ampliación 2026-09-21 — antes solo existía
    `is_active`, siempre obligatorio; se mantiene compatible con eso."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    # Exclusivo del nivel Cadena/Empresa — ver
    # app/billing/domain/plans.py y docs/fase-13-rfc.md §3.3.
    negotiated_included_sessions: int | None = None

    @model_validator(mode="after")
    def _al_menos_un_campo_valido(self) -> PlatformClinicUpdateRequest:
        fields_set = self.model_fields_set
        if not fields_set:
            raise ValueError(
                "Incluye al menos un campo a actualizar (is_active o "
                "negotiated_included_sessions)."
            )
        if "is_active" in fields_set and self.is_active is None:
            raise ValueError("is_active no puede ser null.")
        if (
            "negotiated_included_sessions" in fields_set
            and self.negotiated_included_sessions is not None
            and self.negotiated_included_sessions <= 0
        ):
            raise ValueError(
                "negotiated_included_sessions debe ser un entero positivo, o null para quitarlo."
            )
        return self
