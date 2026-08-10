"""Entidad de dominio AudioRecording. Sin dependencias de SQLAlchemy.

Solo metadatos — el binario nunca se almacena en PostgreSQL, ver
docs/data-model.md §2 (`audio_recordings`). Sin `clinic_id` propio: el
aislamiento por clínica se resuelve siempre a través de
`clinical_session_id` (join contra `clinical_sessions`), igual que
`ai_artifacts` — ver `AudioRecordingRepository`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.processing_status import ProcessingStatus


@dataclass(slots=True)
class AudioRecording:
    id: uuid.UUID
    clinical_session_id: uuid.UUID
    status: ProcessingStatus
    storage_provider: str
    storage_reference: str | None
    original_filename: str
    mime_type: str
    extension: str
    duration_seconds: int | None
    size_bytes: int
    checksum: str
    failure_reason: str | None
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    deleted_at: datetime | None
