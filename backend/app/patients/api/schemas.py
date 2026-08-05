"""Esquemas Pydantic de la API de pacientes.

Deliberadamente separados de PatientORM: la API nunca serializa objetos
SQLAlchemy directamente. Los campos protegidos (clinic_id, created_by,
created_at, id, schema_version...) no existen en los esquemas de
entrada; con `extra="forbid"` cualquier intento de enviarlos se rechaza
con 422 en vez de ignorarse en silencio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.patients.domain.entities import Sex
from app.patients.domain.normalization import normalize_free_text, normalize_internal_code

_INTERNAL_CODE_MAX_LENGTH = 64
_DISPLAY_NAME_MAX_LENGTH = 200
_NOTES_MAX_LENGTH = 2000
_MIN_BIRTH_YEAR = 1900


def _validate_birth_year(value: int | None) -> int | None:
    if value is None:
        return value
    current_year = datetime.now(UTC).year
    if value < _MIN_BIRTH_YEAR or value > current_year:
        raise ValueError(f"birth_year debe estar entre {_MIN_BIRTH_YEAR} y {current_year}.")
    return value


class _PatientBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatientCreateRequest(_PatientBase):
    internal_code: str = Field(min_length=1, max_length=_INTERNAL_CODE_MAX_LENGTH)
    display_name: str | None = Field(default=None, max_length=_DISPLAY_NAME_MAX_LENGTH)
    birth_year: int | None = None
    sex: Sex | None = None
    preferred_language: Literal["es"] = "es"
    notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)

    @field_validator("internal_code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return normalize_internal_code(value)

    @field_validator("display_name", "notes")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_free_text(value)
        return normalized or None

    @field_validator("birth_year")
    @classmethod
    def _check_birth_year(cls, value: int | None) -> int | None:
        return _validate_birth_year(value)


class PatientUpdateRequest(_PatientBase):
    """Todos los campos son opcionales (PATCH parcial).

    Se distingue "campo omitido" (no se toca) de "campo enviado como
    null" (se limpia) mediante `model_dump(exclude_unset=True)` en el
    router, no aquí.
    """

    internal_code: str | None = Field(
        default=None, min_length=1, max_length=_INTERNAL_CODE_MAX_LENGTH
    )
    display_name: str | None = Field(default=None, max_length=_DISPLAY_NAME_MAX_LENGTH)
    birth_year: int | None = None
    sex: Sex | None = None
    preferred_language: Literal["es"] | None = None
    notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)

    @field_validator("internal_code")
    @classmethod
    def _normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return normalize_internal_code(value)

    @field_validator("display_name", "notes")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_free_text(value)
        return normalized or None

    @field_validator("birth_year")
    @classmethod
    def _check_birth_year(cls, value: int | None) -> int | None:
        return _validate_birth_year(value)


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    internal_code: str
    display_name: str | None
    birth_year: int | None
    sex: Sex | None
    preferred_language: str
    notes: str | None
    is_archived: bool
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    schema_version: int


class PatientListResponse(BaseModel):
    items: list[PatientResponse]
    total: int
    limit: int
    offset: int


def update_payload_from_request(request: PatientUpdateRequest) -> dict[str, Any]:
    """Campos explícitamente enviados por el cliente (omite los no enviados)."""
    return request.model_dump(exclude_unset=True)
