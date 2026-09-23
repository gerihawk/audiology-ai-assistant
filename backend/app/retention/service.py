"""RetentionCleanupService: sin puerto propio (a diferencia de
`AudioStorage`/`TranscriptionProvider`) — no hay proveedor que intercambiar
aquí, solo opera sobre `AudioRecordingRepository` y reutiliza
`AudioRecordingService.delete()` para el borrado real, en vez de duplicar
esa lógica. Fase 7.2 (docs/development-plan.md).

`purge_patient_clinical_data()` (añadido 2026-09-18, ver
docs/privacy-and-security.md §8) es una operación distinta y más severa
que `purge()`: mientras `purge()` solo borra audio ya expirado por
antigüedad (y de forma no atómica, fila a fila), esta purga borrado
físico TODO — audio, `ai_artifacts`/`ai_artifact_versions`,
`ai_generation_runs`, `ai_pipeline_runs` y `clinical_sessions` — de UN
paciente concreto, a petición explícita (nunca automática, nunca por
cron), y SÍ es atómica (una única transacción: o se borra todo, o no se
borra nada) porque una purga parcial dejaría referencias huérfanas entre
tablas.

Desde 2026-09-23 (cierre del hallazgo medio del red team,
docs/security/red-team-app-2026-09-22.md: "sin borrado RGPD real de
identidad de paciente") esta misma operación también anonimiza in-place
la fila `patients`: hasta esa fecha, el borrado físico de arriba dejaba
intacta la identidad (`display_name`/`birth_year`/`notes`/
`internal_code`), que solo se archivaba (`is_archived`, reversible), no
se anonimizaba. Ver `PatientORM.identity_purged_at` y
docs/privacy-and-security.md §8.2."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.generation_run_repository import AIGenerationRunRepository
from app.ai_pipeline.domain.pipeline_run_repository import AIPipelineRunRepository
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIArtifactRepository,
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.audio.domain.audio_storage import AudioStorage, StorageReference
from app.audio.domain.entities import AudioRecording
from app.audio.domain.repository import AudioRecordingRepository
from app.audio.infrastructure.local_audio_storage import LocalAudioStorage
from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.audio.service import AudioRecordingService
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.core.authorization import RetentionAction, authorize_retention_action
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.patients.domain.repository import PatientRepository
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository

#: Marcador fijo para `display_name` tras la purga — igual para todo
#: paciente anonimizado, nunca reversible a partir de este valor.
_IDENTITY_ANONYMIZED_DISPLAY_NAME = "[Paciente eliminado]"
#: `internal_code` es NOT NULL (ver docstring de
#: `purge_patient_clinical_data`) — se sustituye por este prefijo + el
#: `patient_id` (único por definición), nunca por `NULL`.
_IDENTITY_ANONYMIZED_INTERNAL_CODE_PREFIX = "eliminado-"


@dataclass(slots=True, frozen=True)
class PatientDataPurgeSummary:
    """Resultado de `purge_patient_clinical_data()` — nº de filas
    eliminadas físicamente por tabla, para la respuesta de la API y el
    audit log."""

    clinical_sessions_purged: int
    ai_artifacts_purged: int
    audio_recordings_purged: int


class RetentionCleanupService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        audio_repository: AudioRecordingRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
        patient_repository: PatientRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        ai_artifact_repository: AIArtifactRepository | None = None,
        ai_generation_run_repository: AIGenerationRunRepository | None = None,
        ai_pipeline_run_repository: AIPipelineRunRepository | None = None,
        audio_storage: AudioStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._audio_recordings = audio_repository or SqlAlchemyAudioRecordingRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._artifacts = ai_artifact_repository or SqlAlchemyAIArtifactRepository()
        self._generation_runs = (
            ai_generation_run_repository or SqlAlchemyAIGenerationRunRepository()
        )
        self._pipeline_runs = ai_pipeline_run_repository or SqlAlchemyAIPipelineRunRepository()
        self._audio_storage = audio_storage or LocalAudioStorage(
            self._settings.audio_storage_local_dir
        )

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

    async def purge_patient_clinical_data(
        self,
        current_user: CurrentUser,
        patient_id: uuid.UUID,
        request_id: str,
        *,
        confirm: bool,
    ) -> PatientDataPurgeSummary:
        """Purga definitiva (física, irreversible) de TODAS las sesiones
        clínicas, artefactos de IA y audio de un paciente — a petición
        explícita de la clínica (responsable del tratamiento), nunca
        automática. Ver docs/privacy-and-security.md §8: cierra el hueco
        de que, hasta ahora, `ai_artifacts`/`clinical_sessions` no tenían
        ningún borrado físico posible, solo lógico.

        `confirm` es obligatorio y debe ser `True` — no hay valor por
        defecto que lo asuma, y el esquema de la API (`Literal[True]`)
        ya lo exige a nivel de transporte; esta comprobación de dominio
        es una segunda barrera para cualquier otro llamador (CLI, tests,
        futuras integraciones).

        Atómica a propósito (a diferencia de `purge()`, ver docstring del
        módulo): borra en el orden que exigen las FK entre tablas —
        1) audio (blob + fila), 2) versiones de artefactos + rotura de
        las referencias circulares de `ai_artifacts`, 3) generation runs,
        4) los propios `ai_artifacts`, 5) pipeline runs, 6) las
        `clinical_sessions`, 7) anonimización in-place de la identidad del
        paciente (`patients`). El `audit_log` se escribe en la misma
        transacción y sobrevive a la purga (`entity_id` sin FK — ver
        `app/audit_log/infrastructure/orm.py`): es la única prueba de que
        estos datos existieron y de quién pidió borrarlos.

        La anonimización de identidad (paso 7) ocurre siempre que se
        confirma la purga, incluso si el paciente no tiene ninguna sesión
        clínica todavía — un paciente puede ejercer su derecho de
        supresión sin haber llegado a tener una consulta, y no hay razón
        para bloquear eso. `patients.internal_code` es `NOT NULL` (a
        diferencia de `display_name`/`birth_year`/`notes`) y se usa como
        `str` no-opcional en la exportación de expedientes
        (`app/export/service.py`, `app/clinical_record/service.py`) y en
        `PatientResponse` (`app/patients/api/schemas.py`): por eso se
        sustituye por un marcador anonimizado único derivado del
        `patient_id`, nunca por `NULL`."""
        authorize_retention_action(current_user, RetentionAction.PURGE_PATIENT_DATA)

        if not confirm:
            raise ConflictError(
                "La purga definitiva de datos clínicos de un paciente exige "
                "confirmación explícita (confirm=true) — es una operación "
                "irreversible."
            )

        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")

        sessions = await self._clinical_sessions.list_all_by_patient(
            self._session, current_user.clinic_id, patient_id
        )
        session_ids = [clinical_session.id for clinical_session in sessions]

        audio_count = 0
        artifact_count = 0
        session_count = 0

        try:
            if session_ids:
                audio_recordings: list[AudioRecording] = (
                    await self._audio_recordings.list_for_sessions(
                        self._session, current_user.clinic_id, session_ids
                    )
                )
                for audio_recording in audio_recordings:
                    if audio_recording.storage_reference is not None:
                        await self._audio_storage.delete(
                            StorageReference(audio_recording.storage_reference)
                        )
                audio_count = await self._audio_recordings.delete_all_for_sessions(
                    self._session, session_ids
                )

                artifact_ids = await self._artifacts.prepare_purge_for_sessions(
                    self._session, current_user.clinic_id, session_ids
                )
                await self._generation_runs.delete_for_sessions(self._session, session_ids)
                artifact_count = await self._artifacts.finish_purge(self._session, artifact_ids)
                await self._pipeline_runs.delete_for_sessions(self._session, session_ids)

                session_count = await self._clinical_sessions.delete_all(
                    self._session, current_user.clinic_id, session_ids
                )

            now = datetime.now(UTC)
            await self._patients.update_fields(
                self._session,
                current_user.clinic_id,
                patient_id,
                {
                    "display_name": _IDENTITY_ANONYMIZED_DISPLAY_NAME,
                    "birth_year": None,
                    "notes": None,
                    "internal_code": f"{_IDENTITY_ANONYMIZED_INTERNAL_CODE_PREFIX}{patient_id}",
                    "is_archived": True,
                    "archived_at": patient.archived_at if patient.is_archived else now,
                    "identity_purged_at": now,
                    "updated_by": current_user.id,
                    "updated_at": now,
                },
            )

            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="retention.patient_data_purged",
                    entity_type="patient",
                    entity_id=patient_id,
                    request_id=request_id,
                    metadata={
                        "clinical_sessions_purged": session_count,
                        "ai_artifacts_purged": artifact_count,
                        "audio_recordings_purged": audio_count,
                        "identity_anonymized": True,
                    },
                ),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return PatientDataPurgeSummary(
            clinical_sessions_purged=session_count,
            ai_artifacts_purged=artifact_count,
            audio_recordings_purged=audio_count,
        )
