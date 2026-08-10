"""Esquemas Pydantic de la API de grabaciones de audio.

`storage_reference` nunca se expone: es un detalle interno de
`AudioStorage`, opaco incluso para el propio dominio de `audio` (ver
domain/audio_storage.py) — con más razón no debe llegar al cliente.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.audio.domain.entities import AudioRecording
from app.core.processing_status import ProcessingStatus


class AudioRecordingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    clinical_session_id: uuid.UUID
    status: ProcessingStatus
    storage_provider: str
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

    @classmethod
    def from_entity(cls, entity: AudioRecording) -> AudioRecordingResponse:
        return cls(
            id=entity.id,
            clinical_session_id=entity.clinical_session_id,
            status=entity.status,
            storage_provider=entity.storage_provider,
            original_filename=entity.original_filename,
            mime_type=entity.mime_type,
            extension=entity.extension,
            duration_seconds=entity.duration_seconds,
            size_bytes=entity.size_bytes,
            checksum=entity.checksum,
            failure_reason=entity.failure_reason,
            uploaded_by=entity.uploaded_by,
            uploaded_at=entity.uploaded_at,
            deleted_at=entity.deleted_at,
        )


class AudioRecordingListResponse(BaseModel):
    items: list[AudioRecordingResponse]
