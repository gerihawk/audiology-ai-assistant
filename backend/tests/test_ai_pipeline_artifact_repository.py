"""Tests de `SqlAlchemyAIArtifactRepository.get_latest_approved` — la
consulta longitudinal mínima de la Fase 6.4.1 (RFC técnico §1/§2,
Decisión final 1). Contra base de datos real de test, sin pasar por
`AIPipelineService` (aislado del resto del pipeline)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
)
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.clinical_sessions.domain.entities import ClinicalSession
from app.patients.domain.entities import Patient
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_clinical_session,
    create_patient,
)

_REPO = SqlAlchemyAIArtifactRepository()


async def _approve_anamnesis(
    session: AsyncSession,
    clinical_session: ClinicalSession,
    *,
    approved_at: datetime,
    content: dict | None = None,
) -> AIArtifact:
    """Crea un `AIArtifact` de tipo ANAMNESIS ya aprobado, replicando lo
    que `AIPipelineService._persist_completed_outcome` +
    `_set_disposition` hacen en producción (nueva versión -> reabre
    review_pending -> aprobar), sin pasar por el servicio completo."""
    artifact_id = uuid.uuid4()
    await _REPO.insert_new(
        session,
        AIArtifact(
            id=artifact_id,
            clinical_session_id=clinical_session.id,
            artifact_type=AIArtifactType.ANAMNESIS,
            status=AIArtifactStatus.REVIEW_PENDING,
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
            created_at=approved_at,
            updated_at=approved_at,
        ),
    )
    version = await _REPO.insert_version(
        session,
        AIArtifactVersion(
            id=uuid.uuid4(),
            ai_artifact_id=artifact_id,
            version_number=1,
            content=(
                content
                if content is not None
                else {"tinnitus": {"value": "sí", "status": "informado"}}
            ),
            confidence=55,
            source_map=None,
            source=AIArtifactVersionSource.AI_GENERATED,
            generation_run_id=None,
            created_by=None,
            change_note=None,
            created_at=approved_at,
        ),
    )
    updated = await _REPO.update_disposition(
        session,
        clinical_session.clinic_id,
        artifact_id,
        {
            "current_version_id": version.id,
            "status": AIArtifactStatus.APPROVED.value,
            "approved_by": clinical_session.professional_id,
            "approved_at": approved_at,
            # `updated_at` tiene `onupdate=func.now()` (solo server-side):
            # sin fijarlo explícitamente aquí, `_artifact_to_domain` lo
            # leería expirado tras el flush y fallaría con
            # `MissingGreenlet` fuera de contexto async — mismo motivo por
            # el que TODOS los call sites de producción en `service.py`
            # ya lo incluyen siempre en `values`.
            "updated_at": approved_at,
        },
    )
    await session.commit()
    assert updated is not None
    return updated


async def _leave_pending(
    session: AsyncSession, clinical_session: ClinicalSession, *, status: AIArtifactStatus
) -> AIArtifact:
    """Crea un artefacto ANAMNESIS que NUNCA llega a `APPROVED` — para
    los casos "review_pending/rejected → nunca" del enunciado."""
    artifact_id = uuid.uuid4()
    now = datetime.now(UTC)
    artifact = await _REPO.insert_new(
        session,
        AIArtifact(
            id=artifact_id,
            clinical_session_id=clinical_session.id,
            artifact_type=AIArtifactType.ANAMNESIS,
            status=AIArtifactStatus.REVIEW_PENDING,
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
        ),
    )
    if status != AIArtifactStatus.REVIEW_PENDING:
        updated = await _REPO.update_disposition(
            session,
            clinical_session.clinic_id,
            artifact_id,
            {"status": status.value, "updated_at": datetime.now(UTC)},
        )
        await session.commit()
        assert updated is not None
        return updated
    await session.commit()
    return artifact


async def test_same_session_with_approved_anamnesis_is_never_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Decisión final 1: la sesión actual nunca cuenta como "previa" de
    sí misma, ni siquiera si ya tiene una anamnesis aprobada."""
    clinical_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _approve_anamnesis(db_session, clinical_session, approved_at=datetime.now(UTC))

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=clinical_session.id,
    )

    assert result is None


async def test_earlier_session_with_approved_anamnesis_is_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    earlier_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    approved = await _approve_anamnesis(
        db_session, earlier_session, approved_at=datetime.now(UTC) - timedelta(days=30)
    )
    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is not None
    assert result.id == approved.id
    assert result.clinical_session_id == earlier_session.id


async def test_multiple_previous_sessions_returns_most_recent_approved_at(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    now = datetime.now(UTC)
    oldest_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _approve_anamnesis(db_session, oldest_session, approved_at=now - timedelta(days=90))

    middle_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    most_recent = await _approve_anamnesis(
        db_session, middle_session, approved_at=now - timedelta(days=1)
    )

    # Una tercera sesión, aprobada hace más tiempo que `middle_session`
    # pero creada/aprobada antes en el calendario que `oldest_session` en
    # términos de sesión — demuestra que gana `approved_at`, no el orden
    # de creación de la fila ni el de la sesión.
    older_but_last_approved_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _approve_anamnesis(
        db_session, older_but_last_approved_session, approved_at=now - timedelta(days=60)
    )

    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is not None
    assert result.id == most_recent.id


async def test_other_patient_same_clinic_is_never_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    other_patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    other_patient_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        other_patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _approve_anamnesis(db_session, other_patient_session, approved_at=datetime.now(UTC))
    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,  # el paciente correcto, no `other_patient`
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is None


async def test_same_patient_other_clinic_is_never_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    other_clinic = await create_clinic_with_users(db_session)
    other_clinic_patient = await create_patient(
        db_session, other_clinic.clinic.id, other_clinic.admin.id
    )
    other_clinic_session = await create_clinical_session(
        db_session,
        other_clinic.clinic.id,
        other_clinic_patient.id,
        other_clinic.audiologist.id,
        other_clinic.admin.id,
    )
    await _approve_anamnesis(db_session, other_clinic_session, approved_at=datetime.now(UTC))
    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,  # la clínica correcta, no `other_clinic`
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is None


async def test_soft_deleted_approved_anamnesis_is_never_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    earlier_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    approved = await _approve_anamnesis(db_session, earlier_session, approved_at=datetime.now(UTC))
    deleted = await _REPO.update_disposition(
        db_session,
        clinic_with_users.clinic.id,
        approved.id,
        {
            "deleted_by": clinic_with_users.admin.id,
            "deleted_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    )
    await db_session.commit()
    assert deleted is not None
    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is None


async def test_review_pending_or_rejected_anamnesis_is_never_returned(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    pending_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _leave_pending(db_session, pending_session, status=AIArtifactStatus.REVIEW_PENDING)

    rejected_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    await _leave_pending(db_session, rejected_session, status=AIArtifactStatus.REJECTED)

    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is None


async def test_no_previous_anamnesis_at_all_returns_none(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )

    result = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=current_session.id,
    )

    assert result is None
