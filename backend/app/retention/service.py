"""RetentionCleanupService: sin puerto propio (a diferencia de
`AudioStorage`/`TranscriptionProvider`) — no hay proveedor que intercambiar
aquí, solo opera sobre `AudioRecordingRepository` y reutiliza
`AudioRecordingService.delete()` para el borrado real, en vez de duplicar
esa lógica. Fase 7.2 (docs/development-plan.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.domain.entities import AudioRecording
from app.audio.domain.repository import AudioRecordingRepository
from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.audio.service import AudioRecordingService
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.core.authorization import RetentionAction, authorize_retention_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser


class RetentionCleanupService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        audio_repository: AudioRecordingRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._audio_recordings = audio_repository or SqlAlchemyAudioRecordingRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    def _cutoff(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self._settings.retention_days_default)

    async def find_expired_audio(self, current_user: CurrentUser) -> list[AudioRecording]:
        authorize_retention_action(current_user, RetentionAction.READ)
        return await self._audio_recordings.list_expired(
            self._session, current_user.clinic_id, self._cutoff()
        )

    async def purge(self, current_user: CurrentUser, request_id: str) -> list[AudioRecording]:
        authorize_retention_action(current_user, RetentionAction.PURGE)
        expired = await self._audio_recordings.list_expired(
            self._session, current_user.clinic_id, self._cutoff()
        )

        # Cada `delete()` reutilizado hace su propio commit — la purga NO
        # es una única transacción atómica (decisión deliberada, ver
        # docs/development-plan.md §Fase 7.2): si un registro falla, los
        # anteriores ya purgados quedan purgados y una purga posterior los
        # ignora (`list_expired` ya no los ve, son `DELETED`).
        audio_service = AudioRecordingService(self._session)
        purged = [
            await audio_service.delete(current_user, audio.id, request_id) for audio in expired
        ]

        if purged:
            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="retention.purge_executed",
                    entity_type="retention_purge",
                    entity_id=uuid.uuid4(),
                    request_id=request_id,
                    metadata={
                        "purged_count": len(purged),
                        "audio_recording_ids": [str(audio.id) for audio in purged],
                    },
                ),
            )
            await self._session.commit()
        return purged
