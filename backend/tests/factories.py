"""Helpers para crear clínicas/usuarios ficticios directamente vía repositorio en los tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
    AIGenerationRun,
    AIGenerationRunStatus,
    AIPipelineRun,
    AIPipelineRunStatus,
)
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIArtifactRepository,
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.audio.domain.entities import AudioRecording
from app.audio.infrastructure.orm import AudioRecordingORM
from app.clinical_sessions.domain.entities import (
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.orm import ClinicORM
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.consents.domain.entities import Consent, ConsentType
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.core.current_user import CurrentUser
from app.core.processing_status import ProcessingStatus
from app.integrations.domain.integration_config import IntegrationConfig, IntegrationName
from app.integrations.infrastructure.orm import IntegrationConfigORM
from app.patients.domain.entities import Patient
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
from app.platform_admin.domain.entities import PlatformOperator
from app.platform_admin.infrastructure.repository import SqlAlchemyPlatformOperatorRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository


def _now() -> datetime:
    return datetime.now(UTC)


async def create_clinic(
    session: AsyncSession,
    *,
    code: str | None = None,
    name: str = "Clínica de test",
    created_at: datetime | None = None,
) -> Clinic:
    """`created_at` explícito (mismo motivo que `uploaded_at` en
    `create_audio_recording`) para poder simular clínicas dadas de alta
    hace tiempo en los tests de `UnverifiedClinicCleanupService` (Fase 12,
    hito 12.4) — `SqlAlchemyClinicRepository.add` nunca lo acepta (siempre
    `server_default=func.now()`), así que un `created_at` explícito
    inserta el `ClinicORM` directamente en vez de pasar por el
    repositorio."""
    resolved_created_at = created_at or _now()
    clinic = Clinic(
        id=uuid.uuid4(),
        name=name,
        code=code or f"TEST-{uuid.uuid4().hex[:8]}",
        is_active=True,
        created_at=resolved_created_at,
        updated_at=_now(),
    )
    if created_at is None:
        await SqlAlchemyClinicRepository().add(session, clinic)
    else:
        session.add(
            ClinicORM(
                id=clinic.id,
                name=clinic.name,
                code=clinic.code,
                is_active=clinic.is_active,
                created_at=resolved_created_at,
            )
        )
    await session.commit()
    return clinic


def hash_password(password: str) -> str:
    """Mismo algoritmo que `app.seed`/`AuthService` — helper de test para
    no repetir `bcrypt.hashpw(...).decode(...)` en cada test de Fase 9."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def create_user(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    *,
    role: Role,
    email: str | None = None,
    display_name: str | None = None,
    is_active: bool = True,
    password: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.local",
        display_name=display_name or f"Usuario {role.value} de test",
        role=role,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
        password_hash=hash_password(password) if password is not None else None,
    )
    await SqlAlchemyUserRepository().add(session, user)
    await session.commit()
    return user


@dataclass(slots=True)
class ClinicWithUsers:
    clinic: Clinic
    admin: User
    audiologist: User
    viewer: User


async def create_clinic_with_users(session: AsyncSession) -> ClinicWithUsers:
    clinic = await create_clinic(session)
    admin = await create_user(session, clinic.id, role=Role.ADMIN)
    audiologist = await create_user(session, clinic.id, role=Role.AUDIOLOGIST)
    viewer = await create_user(session, clinic.id, role=Role.VIEWER)
    return ClinicWithUsers(clinic=clinic, admin=admin, audiologist=audiologist, viewer=viewer)


async def create_patient(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    internal_code: str | None = None,
    is_archived: bool = False,
) -> Patient:
    patient = Patient(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        internal_code=internal_code or f"PAT-{uuid.uuid4().hex[:8].upper()}",
        display_name="Paciente de test",
        birth_year=1980,
        sex=None,
        preferred_language="es",
        notes=None,
        is_archived=is_archived,
        created_by=created_by,
        updated_by=created_by,
        created_at=_now(),
        updated_at=_now(),
        archived_at=_now() if is_archived else None,
        schema_version=1,
    )
    await SqlAlchemyPatientRepository().add(session, patient)
    await session.commit()
    return patient


async def create_consent(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    granted_by: uuid.UUID,
    *,
    clinical_session_id: uuid.UUID | None = None,
    consent_type: ConsentType = ConsentType.PROCESAMIENTO_IA,
    granted: bool = True,
) -> Consent:
    consent = Consent(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        clinical_session_id=clinical_session_id,
        consent_type=consent_type,
        granted=granted,
        consent_version=None,
        granted_by=granted_by,
        recorded_at=None,
        notes=None,
    )
    persisted = await SqlAlchemyConsentRepository().add(session, consent)
    await session.commit()
    return persisted


async def create_clinical_session(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    professional_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    session_type: SessionType = SessionType.INITIAL_ASSESSMENT,
    status: ClinicalSessionStatus = ClinicalSessionStatus.COMPLETED,
) -> ClinicalSession:
    clinical_session = ClinicalSession(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        professional_id=professional_id,
        session_type=session_type,
        status=status,
        scheduled_at=None,
        started_at=None,
        ended_at=None,
        title=None,
        administrative_notes=None,
        reviewed_by=None,
        reviewed_at=None,
        created_by=created_by,
        updated_by=created_by,
        created_at=_now(),
        updated_at=_now(),
        schema_version=1,
        is_archived=False,
        archived_at=None,
    )
    await SqlAlchemyClinicalSessionRepository().add(session, clinical_session)
    await session.commit()
    return clinical_session


async def create_audio_recording(
    session: AsyncSession,
    clinical_session_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    *,
    status: ProcessingStatus = ProcessingStatus.READY,
    uploaded_at: datetime | None = None,
) -> AudioRecording:
    """`uploaded_at` explícito (no `server_default`) para poder simular
    audio antiguo en los tests de retención (Fase 7.2)."""
    row = AudioRecordingORM(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        status=status.value,
        storage_provider="local",
        storage_reference=f"audio/{uuid.uuid4().hex}.mp3",
        original_filename="consulta_ficticia.mp3",
        mime_type="audio/mpeg",
        extension="mp3",
        duration_seconds=30,
        size_bytes=1024,
        checksum=uuid.uuid4().hex,
        failure_reason=None,
        uploaded_by=uploaded_by,
        uploaded_at=uploaded_at or _now(),
        deleted_at=None,
    )
    session.add(row)
    await session.commit()
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


async def create_integration_config(
    session: AsyncSession,
    integration_name: IntegrationName,
    updated_by: uuid.UUID,
    *,
    active_provider: str = "mock",
    enabled: bool = False,
) -> IntegrationConfig:
    row = IntegrationConfigORM(
        id=uuid.uuid4(),
        integration_name=integration_name.value,
        active_provider=active_provider,
        enabled=enabled,
        updated_by=updated_by,
    )
    session.add(row)
    await session.commit()
    return IntegrationConfig(
        id=row.id,
        integration_name=IntegrationName(row.integration_name),
        active_provider=row.active_provider,
        enabled=row.enabled,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


async def create_ai_artifact_with_version(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    clinical_session_id: uuid.UUID,
    triggered_by: uuid.UUID,
    *,
    artifact_type: AIArtifactType = AIArtifactType.SUMMARY,
    status: AIArtifactStatus = AIArtifactStatus.APPROVED,
) -> AIArtifact:
    """Crea un `AIPipelineRun` + `AIGenerationRun` + `AIArtifact` +
    `AIArtifactVersion` completos y enlazados entre sí (incluido
    `current_version_id`) — mismo grafo de tablas que produce un pipeline
    real, para tests que necesiten un artefacto de IA de verdad (p. ej.
    la purga definitiva de datos de paciente, Fase de retención,
    docs/privacy-and-security.md §8)."""
    now = _now()

    pipeline_run = AIPipelineRun(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        triggered_by=triggered_by,
        status=AIPipelineRunStatus.COMPLETED,
        started_at=now,
        completed_at=now,
        request_id=None,
    )
    await SqlAlchemyAIPipelineRunRepository().add(session, pipeline_run)

    artifact = AIArtifact(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        artifact_type=artifact_type,
        status=status,
        current_version_id=None,
        confidence=None,
        schema_version=1,
        approved_by=None,
        approved_at=None,
        rejected_by=None,
        rejected_at=None,
        rejection_reason=None,
        deleted_by=None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyAIArtifactRepository().insert_new(session, artifact)

    generation_run = AIGenerationRun(
        id=uuid.uuid4(),
        ai_pipeline_run_id=pipeline_run.id,
        clinical_session_id=clinical_session_id,
        artifact_type=artifact_type,
        ai_artifact_id=artifact.id,
        resulting_version_number=1,
        status=AIGenerationRunStatus.COMPLETED,
        provider_name="mock",
        model_name=None,
        prompt_template_id=None,
        prompt_template_version=None,
        input_token_count=None,
        output_token_count=None,
        estimated_cost_usd=None,
        latency_ms=None,
        execution_time_ms=None,
        rendered_system_prompt=None,
        rendered_user_prompt=None,
        raw_response=None,
        started_at=now,
        completed_at=now,
        failure_reason=None,
        request_id=None,
    )
    await SqlAlchemyAIGenerationRunRepository().add(session, generation_run)

    version = AIArtifactVersion(
        id=uuid.uuid4(),
        ai_artifact_id=artifact.id,
        version_number=1,
        content={"text": "Contenido ficticio de test."},
        confidence=None,
        source_map=None,
        source=AIArtifactVersionSource.AI_GENERATED,
        generation_run_id=generation_run.id,
        created_by=None,
        change_note=None,
        created_at=now,
    )
    await SqlAlchemyAIArtifactRepository().insert_version(session, version)

    updated = await SqlAlchemyAIArtifactRepository().update_disposition(
        session,
        clinic_id,
        artifact.id,
        # `updated_at` explícito, no confiar en `onupdate=func.now()`: sin
        # esto, SQLAlchemy expira la columna tras el UPDATE y el acceso
        # síncrono posterior a `.updated_at` en `_artifact_to_domain()`
        # dispara un `MissingGreenlet` (mismo motivo por el que
        # `AIPipelineService.delete_artifact` ya pasa `updated_at`
        # explícito junto a `deleted_at`/`deleted_by`).
        {"current_version_id": version.id, "updated_at": now},
    )
    await session.commit()
    assert updated is not None
    return updated


async def create_platform_operator(
    session: AsyncSession,
    *,
    email: str | None = None,
    display_name: str = "Operador de test",
    is_active: bool = True,
    password: str | None = None,
) -> PlatformOperator:
    """Helper de la Fase 14 (panel de gestión de clínicas del operador de
    la plataforma) — mismo patrón que `create_user`, pero sobre
    `platform_operators`, tabla completamente aparte de `users`."""
    operator = PlatformOperator(
        id=uuid.uuid4(),
        email=email or f"operador-{uuid.uuid4().hex[:8]}@test.local",
        display_name=display_name,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
        password_hash=hash_password(password) if password is not None else None,
    )
    await SqlAlchemyPlatformOperatorRepository().add(session, operator)
    await session.commit()
    return operator


def dev_headers(user: User) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


def current_user_from(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        clinic_id=user.clinic_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
