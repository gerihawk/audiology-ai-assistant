"""Esquemas Pydantic de invitaciones (Fase 12, hitos 12.2/12.3).

Mismo criterio que `app.onboarding.api.schemas`: normalización/validación
de entrada en `@field_validator`s que delegan en
`app.onboarding.domain.normalization`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator

from app.onboarding.domain.entities import Invitation
from app.onboarding.domain.normalization import (
    normalize_email,
    normalize_required_free_text,
    validate_password_length,
)

_DISPLAY_NAME_FIELD = "display_name"

#: `Literal`, no el `StrEnum` completo `Role`: excluye `admin` a nivel de
#: esquema, no solo de lógica de negocio — un valor `"admin"` en el body
#: se rechaza con 422 nativo de Pydantic antes de llegar a
#: `InvitationService` (que revalida contra `INVITABLE_ROLES` de forma
#: defensiva, ver su docstring). Ver docs/fase-12-rfc.md §4.2.
InvitableRoleLiteral = Literal["audiologist", "viewer"]


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    role: InvitableRoleLiteral

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class InvitationAcceptRequest(BaseModel):
    """`token` no es un campo del body: llega por la ruta (`POST
    /invitations/{token}/accept`, ver docs/fase-12-rfc.md §4.2) — a
    diferencia de `VerifyEmailRequest`/`PasswordResetConfirmRequest`
    (hito 12.1), cuyas rutas no lo llevan."""

    model_config = ConfigDict(extra="forbid")

    new_password: str
    display_name: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, value: str) -> str:
        return validate_password_length(value)

    @field_validator("display_name")
    @classmethod
    def _normalize_display_name(cls, value: str) -> str:
        return normalize_required_free_text(value, field_name=_DISPLAY_NAME_FIELD)


class InvitationSummaryResponse(BaseModel):
    """Fase 12, hito 12.3 — respuesta de `GET
    /clinics/{clinic_id}/invitations`, siempre invitaciones pendientes
    (ver `SqlAlchemyInvitationRepository.list_pending_for_clinic`).

    `is_expired` se calcula aquí, no en el dominio: `Invitation.is_usable`
    ya combina caducidad + `accepted_at`, pero para una fila que YA se sabe
    pendiente (`accepted_at IS NULL`, garantizado por el repositorio) la
    única pregunta que le queda al frontend es "¿puede seguir esperando a
    que la acepten, o toca reenviar?" — de ahí exponer solo la caducidad,
    sin repetir aquí la noción de "usable" que ya no aporta nada distinto.
    """

    id: uuid.UUID
    email: str
    role: InvitableRoleLiteral
    expires_at: datetime
    created_at: datetime
    is_expired: bool

    @classmethod
    def from_domain(cls, invitation: Invitation) -> Self:
        return cls(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role.value,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            is_expired=datetime.now(UTC) >= invitation.expires_at,
        )


class InvitationListResponse(BaseModel):
    items: list[InvitationSummaryResponse]
