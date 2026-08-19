"""Esquemas Pydantic de la API de consentimientos — Fase 7.1.

`consent_version` y `clinical_session_id` no existen en
`ConsentCreateRequest`: con `extra="forbid"`, cualquier intento de
enviarlos se rechaza con 422 — mismo criterio que `reviewed_by`/
`reviewed_at` en `clinical_sessions/api/schemas.py` (los fija siempre el
servidor, nunca el cliente).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.consents.domain.entities import ConsentType

_NOTES_MAX_LENGTH = 2000


class ConsentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_type: ConsentType
    granted: bool
    notes: str | None = Field(default=None, max_length=_NOTES_MAX_LENGTH)


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    clinical_session_id: uuid.UUID | None
    consent_type: ConsentType
    granted: bool
    consent_version: str | None
    granted_by: uuid.UUID
    recorded_at: datetime | None
    notes: str | None


class ConsentListResponse(BaseModel):
    items: list[ConsentResponse]
