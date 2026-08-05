"""Entidad de dominio ClinicalSession y sus enums. Sin dependencias de SQLAlchemy.

Sin contenido clínico real: `administrative_notes` es estrictamente
administrativo, igual que `patients.notes` (ver docs/data-model.md §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SessionType(StrEnum):
    INITIAL_ASSESSMENT = "initial_assessment"
    FOLLOW_UP = "follow_up"
    HEARING_AID_FITTING = "hearing_aid_fitting"
    HEARING_AID_ADJUSTMENT = "hearing_aid_adjustment"
    REVIEW = "review"
    OTHER = "other"


class ClinicalSessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REVIEW_PENDING = "review_pending"
    REVIEWED = "reviewed"
    CANCELLED = "cancelled"


#: Estados válidos como valor inicial en la creación (ver data-model.md §8).
CREATABLE_STATUSES: frozenset[ClinicalSessionStatus] = frozenset(
    {
        ClinicalSessionStatus.SCHEDULED,
        ClinicalSessionStatus.IN_PROGRESS,
        ClinicalSessionStatus.COMPLETED,
    }
)


@dataclass(slots=True)
class ClinicalSession:
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
