"""Esquemas Pydantic del onboarding self-service (Fase 12, hito 12.1).

Mismo criterio que `app.patients.api.schemas`: la normalización/validación
de entrada vive en `@field_validator`s que delegan en
`app.onboarding.domain.normalization` — así un valor inválido se rechaza
con 422 (`RequestValidationError` de Pydantic) antes de llegar a
`OnboardingService`, que revalida las mismas reglas de forma defensiva
para cualquier llamador que no pase por la API HTTP.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.onboarding.domain.normalization import (
    normalize_email,
    normalize_required_free_text,
    validate_password_length,
)

_CLINIC_NAME_FIELD = "clinic_name"
_ADMIN_DISPLAY_NAME_FIELD = "admin_display_name"


class ClinicSignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_name: str
    admin_email: str
    admin_display_name: str
    admin_password: str

    @field_validator("clinic_name")
    @classmethod
    def _normalize_clinic_name(cls, value: str) -> str:
        return normalize_required_free_text(value, field_name=_CLINIC_NAME_FIELD)

    @field_validator("admin_display_name")
    @classmethod
    def _normalize_admin_display_name(cls, value: str) -> str:
        return normalize_required_free_text(value, field_name=_ADMIN_DISPLAY_NAME_FIELD)

    @field_validator("admin_email")
    @classmethod
    def _normalize_admin_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("admin_password")
    @classmethod
    def _check_admin_password(cls, value: str) -> str:
        return validate_password_length(value)


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str


class PasswordResetRequestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, value: str) -> str:
        return validate_password_length(value)
