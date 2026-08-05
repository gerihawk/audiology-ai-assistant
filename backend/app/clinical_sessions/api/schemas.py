"""Esquemas Pydantic de la API de sesiones clínicas.

Deliberadamente separados de ClinicalSessionORM. Los campos gestionados
por el servidor (`clinic_id`, `status`, `started_at`, `ended_at`,
`reviewed_by`, `reviewed_at`, `created_by`, `created_at`, `updated_at`,
`id`, `schema_version`, `is_archived`, `archived_at`) no existen en los
esquemas de entrada; con `extra="forbid"` cualquier intento de enviarlos
se rechaza con 422.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.clinical_sessions.domain.entities import ClinicalSessionStatus, SessionType
from app.clinical_sessions.domain.normalization import normalize_free_text

_TITLE_MAX_LENGTH = 200
_NOTES_MAX_LENGTH = 2000


class _ClinicalSessionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClinicalSessionCreateRequest(_ClinicalSessionBase):
    patient_id: uuid.UUID
    professional_id: uuid.UUID
    session_type: SessionType
    status: Literal["scheduled", "in_progress", "completed"] = "scheduled"
    scheduled_at: datetime | None = None
    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)
    administrative_notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)

    @field_validator("title", "administrative_notes")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_free_text(value)
        return normalized or None


class ClinicalSessionUpdateRequest(_ClinicalSessionBase):
    """Todos los campos son opcionales (PATCH parcial).

    `professional_id` está presente en el esquema porque puede llegar a
    editarse (sujeto a autorización de `CHANGE_PROFESSIONAL` y a la
    ventana de estados editables) — no así `patient_id`, `clinic_id` ni
    `status`, que nunca existen aquí.
    """

    session_type: SessionType | None = None
    scheduled_at: datetime | None = None
    title: str | None = Field(default=None, max_length=_TITLE_MAX_LENGTH)
    administrative_notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)
    professional_id: uuid.UUID | None = None

    @field_validator("title", "administrative_notes")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_free_text(value)
        return normalized or None


class ClinicalSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    professional_id: uuid.UUID
    session_type: SessionType
    status: ClinicalSessionStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    title: str | None
    administrative_notes: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    schema_version: int
    is_archived: bool
    archived_at: datetime | None


class ClinicalSessionListResponse(BaseModel):
    items: list[ClinicalSessionResponse]
    total: int
    limit: int
    offset: int


def update_payload_from_request(request: ClinicalSessionUpdateRequest) -> dict[str, Any]:
    """Campos explícitamente enviados por el cliente (omite los no enviados)."""
    return request.model_dump(exclude_unset=True)
