"""Entidad de dominio Patient y enum Sex. Sin dependencias de SQLAlchemy.

Identidad y datos administrativos mínimos del paciente ficticio.
Deliberadamente sin ningún campo clínico (ver docs/data-model.md §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


@dataclass(slots=True)
class Patient:
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
