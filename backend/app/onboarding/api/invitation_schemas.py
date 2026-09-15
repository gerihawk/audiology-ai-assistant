"""Esquemas Pydantic de invitaciones (Fase 12, hito 12.2).

Mismo criterio que `app.onboarding.api.schemas`: normalización/validación
de entrada en `@field_validator`s que delegan en
`app.onboarding.domain.normalization`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

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
