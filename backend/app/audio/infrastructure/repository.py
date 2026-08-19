"""Implementación SQLAlchemy del repositorio de grabaciones de audio.

Aislamiento por clínica mediante join contra `clinical_sessions` en cada
consulta (`audio_recordings` no tiene `clinic_id` propio — ver
domain/repository.py): un `clinical_session_id` de otra clínica nunca
devuelve filas, exactamente igual que si el audio no existiera.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.domain.entities import AudioRecording
from app.audio.infrastructure.orm import AudioRecordingORM
from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM
from app.core.processing_status import ProcessingStatus


def _to_domain(row: AudioRecordingORM) -> AudioRecording:
    return AudioRecording(
        id=row.id,
        clinical_session_id=row.clinical_session_id,
        status=ProcessingStatus(row.status),
        storage_provider=row.storage_provider,
        storage_reference=row.storage_reference,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        extension=row.extension,
        duration_seconds=row.duration_seconds,
        size_bytes=row.size_bytes,
        checksum=row.checksum,
        failure_reason=row.failure_reason,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at,
        deleted_at=row.deleted_at,
    )


class SqlAlchemyAudioRecordingRepository:
    async def add(self, session: AsyncSession, audio_recording: AudioRecording) -> AudioRecording:
        row = AudioRecordingORM(
            id=audio_recording.id,
            clinical_session_id=audio_recording.clinical_session_id,
            status=audio_recording.status.value,
            storage_provider=audio_recording.storage_provider,
            storage_reference=audio_recording.storage_reference,
            original_filename=audio_recording.original_filename,
            mime_type=audio_recording.mime_type,
            extension=audio_recording.extension,
            duration_seconds=audio_recording.duration_seconds,
            size_bytes=audio_recording.size_bytes,
            checksum=audio_recording.checksum,
            failure_reason=audio_recording.failure_reason,
            uploaded_by=audio_recording.uploaded_by,
            deleted_at=audio_recording.deleted_at,
        )
        session.add(row)
        await session.flush()
        return _to_domain(row)

    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, audio_recording_id: uuid.UUID
    ) -> AudioRecording | None:
        result = await session.execute(
            select(AudioRecordingORM)
            .join(
                ClinicalSessionORM,
                ClinicalSessionORM.id == AudioRecordingORM.clinical_session_id,
            )
            .where(
                AudioRecordingORM.id == audio_recording_id,
                ClinicalSessionORM.clinic_id == clinic_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_by_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> list[AudioRecording]:
        result = await session.execute(
            select(AudioRecordingORM)
            .join(
                ClinicalSessionORM,
                ClinicalSessionORM.id == AudioRecordingORM.clinical_session_id,
            )
            .where(
                AudioRecordingORM.clinical_session_id == clinical_session_id,
                ClinicalSessionORM.clinic_id == clinic_id,
            )
            .order_by(AudioRecordingORM.uploaded_at.desc())
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def get_latest_transcribable(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> AudioRecording | None:
        result = await session.execute(
            select(AudioRecordingORM)
            .join(
                ClinicalSessionORM,
                ClinicalSessionORM.id == AudioRecordingORM.clinical_session_id,
            )
            .where(
                AudioRecordingORM.clinical_session_id == clinical_session_id,
                ClinicalSessionORM.clinic_id == clinic_id,
                AudioRecordingORM.status.in_(
                    [ProcessingStatus.READY.value, ProcessingStatus.TRANSCRIBED.value]
                ),
            )
            .order_by(AudioRecordingORM.uploaded_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        audio_recording_id: uuid.UUID,
        values: dict[str, Any],
    ) -> AudioRecording | None:
        result = await session.execute(
            select(AudioRecordingORM)
            .join(
                ClinicalSessionORM,
                ClinicalSessionORM.id == AudioRecordingORM.clinical_session_id,
            )
            .where(
                AudioRecordingORM.id == audio_recording_id,
                ClinicalSessionORM.clinic_id == clinic_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if isinstance(value, ProcessingStatus):
                value = value.value
            setattr(row, key, value)
        await session.flush()
        return _to_domain(row)

    async def list_expired(
        self, session: AsyncSession, clinic_id: uuid.UUID, cutoff: datetime
    ) -> list[AudioRecording]:
        result = await session.execute(
            select(AudioRecordingORM)
            .join(
                ClinicalSessionORM,
                ClinicalSessionORM.id == AudioRecordingORM.clinical_session_id,
            )
            .where(
                ClinicalSessionORM.clinic_id == clinic_id,
                AudioRecordingORM.status != ProcessingStatus.DELETED.value,
                AudioRecordingORM.uploaded_at < cutoff,
            )
            .order_by(AudioRecordingORM.uploaded_at.asc())
        )
        return [_to_domain(row) for row in result.scalars().all()]
