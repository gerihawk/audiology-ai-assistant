"""AudioRecordingService: autoriza → valida → almacena → audita → commit.

Mismo patrón transaccional que ClinicalSessionService/PatientService. La
subida nunca lanza una excepción por un fichero inválido: persiste el
registro en `failed` con `failure_reason`, igual que un paso del AI
Pipeline ante un fallo de proveedor (ver
docs/ai-pipeline-architecture.md §8) — la subida en sí siempre "tiene
éxito" como operación HTTP (201), lo que puede fallar es la validación del
contenido.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.domain.audio_storage import AudioStorage, StorageReference
from app.audio.domain.entities import AudioRecording
from app.audio.domain.repository import AudioRecordingRepository
from app.audio.domain.validation import find_upload_validation_error
from app.audio.infrastructure.local_audio_storage import LocalAudioStorage
from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.core.authorization import AudioRecordingAction, authorize_audio_recording_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import NotFoundError
from app.core.processing_status import ProcessingStatus


@dataclass(slots=True)
class AudioUploadData:
    original_filename: str
    mime_type: str
    content: bytes
    duration_seconds: int


class AudioRecordingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        audio_repository: AudioRecordingRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        audio_storage: AudioStorage | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._audio_recordings = audio_repository or SqlAlchemyAudioRecordingRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._storage = audio_storage or LocalAudioStorage(self._settings.audio_storage_local_dir)
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def upload(
        self,
        current_user: CurrentUser,
        clinical_session_id: uuid.UUID,
        data: AudioUploadData,
        request_id: str,
    ) -> AudioRecording:
        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, clinical_session_id
        )
        if clinical_session is None:
            raise NotFoundError("Sesión clínica no encontrada.")
        authorize_audio_recording_action(
            current_user,
            AudioRecordingAction.UPLOAD,
            professional_id=clinical_session.professional_id,
        )

        extension = _extension_from_filename(data.original_filename)
        size_bytes = len(data.content)
        failure_reason = find_upload_validation_error(
            mime_type=data.mime_type,
            extension=extension,
            size_bytes=size_bytes,
            duration_seconds=data.duration_seconds,
            settings=self._settings,
        )

        storage_reference: StorageReference | None = None
        if failure_reason is None:
            storage_reference = await self._storage.save(
                filename=data.original_filename, content=data.content
            )

        now = datetime.now(UTC)
        new_recording = AudioRecording(
            id=uuid.uuid4(),
            clinical_session_id=clinical_session_id,
            status=ProcessingStatus.FAILED if failure_reason else ProcessingStatus.READY,
            storage_provider=self._settings.audio_storage_provider,
            storage_reference=storage_reference.value if storage_reference else None,
            original_filename=data.original_filename,
            mime_type=data.mime_type,
            extension=extension,
            duration_seconds=None if failure_reason else data.duration_seconds,
            size_bytes=size_bytes,
            checksum=hashlib.sha256(data.content).hexdigest(),
            failure_reason=failure_reason,
            uploaded_by=current_user.id,
            uploaded_at=now,
            deleted_at=None,
        )

        try:
            persisted = await self._audio_recordings.add(self._session, new_recording)
            await self._write_audit(
                current_user,
                request_id,
                action="audio_recording.uploaded",
                entity_id=persisted.id,
                metadata={"status": persisted.status.value, "failure_reason": failure_reason},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return persisted

    async def list_for_session(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID
    ) -> list[AudioRecording]:
        authorize_audio_recording_action(current_user, AudioRecordingAction.READ)
        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, clinical_session_id
        )
        if clinical_session is None:
            raise NotFoundError("Sesión clínica no encontrada.")
        return await self._audio_recordings.list_by_session(
            self._session, current_user.clinic_id, clinical_session_id
        )

    async def delete(
        self, current_user: CurrentUser, audio_recording_id: uuid.UUID, request_id: str
    ) -> AudioRecording:
        existing = await self._audio_recordings.get_by_id(
            self._session, current_user.clinic_id, audio_recording_id
        )
        if existing is None:
            raise NotFoundError("Grabación de audio no encontrada.")

        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, existing.clinical_session_id
        )
        assert clinical_session is not None  # invariante: el audio solo existe si la sesión existe
        authorize_audio_recording_action(
            current_user,
            AudioRecordingAction.DELETE,
            professional_id=clinical_session.professional_id,
        )

        if existing.status == ProcessingStatus.DELETED:
            return existing  # no-op idempotente

        if existing.storage_reference is not None:
            await self._storage.delete(StorageReference(existing.storage_reference))

        try:
            updated = await self._audio_recordings.update_fields(
                self._session,
                current_user.clinic_id,
                existing.id,
                {
                    "status": ProcessingStatus.DELETED.value,
                    "storage_reference": None,
                    "deleted_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user, request_id, action="audio_recording.deleted", entity_id=existing.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def _write_audit(
        self,
        current_user: CurrentUser,
        request_id: str,
        *,
        action: str,
        entity_id: uuid.UUID,
        metadata: dict | None = None,
    ) -> None:
        await self._audit.add(
            self._session,
            AuditLogEntry(
                id=uuid.uuid4(),
                clinic_id=current_user.clinic_id,
                actor_user_id=current_user.id,
                action=action,
                entity_type="audio_recording",
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
            ),
        )


def _extension_from_filename(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()
