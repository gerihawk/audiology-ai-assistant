"""RetentionCleanupService.purge_patient_clinical_data() — purga definitiva
(física, irreversible) de sesiones clínicas/artefactos de IA/audio de un
paciente. Añadido 2026-09-18, ver docs/privacy-and-security.md §8.

Distinto de test_retention_repository.py/test_retention_api.py (que
cubren `purge()`, la purga de audio expirado por antigüedad): aquí se
verifica el borrado físico en cascada de TODAS las tablas implicadas, la
atomicidad, los permisos y la auditoría."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.infrastructure.orm import (
    AIArtifactORM,
    AIArtifactVersionORM,
    AIGenerationRunORM,
    AIPipelineRunORM,
)
from app.audio.infrastructure.orm import AudioRecordingORM
from app.audit_log.infrastructure.orm import AuditLogORM
from app.clinical_sessions.domain.entities import ClinicalSession
from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.patients.domain.entities import Patient
from app.retention.service import RetentionCleanupService
from tests.factories import (
    ClinicWithUsers,
    create_ai_artifact_with_version,
    create_audio_recording,
    create_clinical_session,
    create_patient,
    current_user_from,
)


@pytest_asyncio.fixture
async def clinical_session(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
) -> ClinicalSession:
    return await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )


async def _seed_full_patient_data(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
) -> None:
    await create_audio_recording(db_session, clinical_session.id, clinic_with_users.admin.id)
    await create_ai_artifact_with_version(
        db_session,
        clinic_with_users.clinic.id,
        clinical_session.id,
        clinic_with_users.audiologist.id,
    )


async def _counts(db_session: AsyncSession, clinical_session_id: uuid.UUID) -> dict[str, int]:
    async def _count(stmt) -> int:
        result = await db_session.execute(stmt)
        return len(result.scalars().all())

    return {
        "clinical_sessions": await _count(
            select(ClinicalSessionORM.id).where(ClinicalSessionORM.id == clinical_session_id)
        ),
        "audio_recordings": await _count(
            select(AudioRecordingORM.id).where(
                AudioRecordingORM.clinical_session_id == clinical_session_id
            )
        ),
        "ai_artifacts": await _count(
            select(AIArtifactORM.id).where(AIArtifactORM.clinical_session_id == clinical_session_id)
        ),
        "ai_artifact_versions": await _count(
            select(AIArtifactVersionORM.id)
            .join(AIArtifactORM, AIArtifactVersionORM.ai_artifact_id == AIArtifactORM.id)
            .where(AIArtifactORM.clinical_session_id == clinical_session_id)
        ),
        "ai_generation_runs": await _count(
            select(AIGenerationRunORM.id).where(
                AIGenerationRunORM.clinical_session_id == clinical_session_id
            )
        ),
        "ai_pipeline_runs": await _count(
            select(AIPipelineRunORM.id).where(
                AIPipelineRunORM.clinical_session_id == clinical_session_id
            )
        ),
    }


async def test_purge_deletes_everything_across_all_tables(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    clinical_session: ClinicalSession,
):
    await _seed_full_patient_data(db_session, clinic_with_users, clinical_session)
    before = await _counts(db_session, clinical_session.id)
    assert all(count > 0 for count in before.values()), before

    service = RetentionCleanupService(db_session)
    summary = await service.purge_patient_clinical_data(
        current_user_from(clinic_with_users.admin), patient.id, "req-1", confirm=True
    )

    assert summary.clinical_sessions_purged == 1
    assert summary.ai_artifacts_purged == 1
    assert summary.audio_recordings_purged == 1

    after = await _counts(db_session, clinical_session.id)
    assert all(count == 0 for count in after.values()), after


async def test_purge_writes_audit_log_entry(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    clinical_session: ClinicalSession,
):
    await _seed_full_patient_data(db_session, clinic_with_users, clinical_session)

    service = RetentionCleanupService(db_session)
    await service.purge_patient_clinical_data(
        current_user_from(clinic_with_users.admin), patient.id, "req-audit", confirm=True
    )

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.action == "retention.patient_data_purged")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entity_type == "patient"
    assert entry.entity_id == patient.id
    assert entry.actor_user_id == clinic_with_users.admin.id
    assert entry.request_id == "req-audit"
    assert entry.audit_metadata["clinical_sessions_purged"] == 1
    assert entry.audit_metadata["ai_artifacts_purged"] == 1
    assert entry.audit_metadata["audio_recordings_purged"] == 1


async def test_purge_does_not_touch_other_patients_data(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    clinical_session: ClinicalSession,
):
    await _seed_full_patient_data(db_session, clinic_with_users, clinical_session)

    other_patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    other_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        other_patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _seed_full_patient_data(db_session, clinic_with_users, other_session)

    service = RetentionCleanupService(db_session)
    await service.purge_patient_clinical_data(
        current_user_from(clinic_with_users.admin), patient.id, "req-isolation", confirm=True
    )

    purged_patient_counts = await _counts(db_session, clinical_session.id)
    other_patient_counts = await _counts(db_session, other_session.id)
    assert all(count == 0 for count in purged_patient_counts.values())
    assert all(count > 0 for count in other_patient_counts.values())


async def test_purge_without_confirm_raises_conflict_and_deletes_nothing(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    clinical_session: ClinicalSession,
):
    await _seed_full_patient_data(db_session, clinic_with_users, clinical_session)

    service = RetentionCleanupService(db_session)
    with pytest.raises(ConflictError):
        await service.purge_patient_clinical_data(
            current_user_from(clinic_with_users.admin), patient.id, "req-no-confirm", confirm=False
        )

    after = await _counts(db_session, clinical_session.id)
    assert all(count > 0 for count in after.values()), after


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_purge_forbidden_for_non_admin(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    role_attr: str,
):
    user = getattr(clinic_with_users, role_attr)
    service = RetentionCleanupService(db_session)
    with pytest.raises(ForbiddenError):
        await service.purge_patient_clinical_data(
            current_user_from(user), patient.id, "req-forbidden", confirm=True
        )


async def test_purge_unknown_patient_raises_not_found(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    service = RetentionCleanupService(db_session)
    with pytest.raises(NotFoundError):
        await service.purge_patient_clinical_data(
            current_user_from(clinic_with_users.admin), uuid.uuid4(), "req-404", confirm=True
        )


async def test_purge_patient_without_sessions_is_a_no_op(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    service = RetentionCleanupService(db_session)
    summary = await service.purge_patient_clinical_data(
        current_user_from(clinic_with_users.admin), patient.id, "req-empty", confirm=True
    )

    assert summary.clinical_sessions_purged == 0
    assert summary.ai_artifacts_purged == 0
    assert summary.audio_recordings_purged == 0
