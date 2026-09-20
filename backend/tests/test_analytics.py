"""Tests de la Fase 15 — analítica/reporting para la clínica
(`app.analytics`). Cubre: vista "clinic" de `ADMIN` (pacientes,
desglose de sesiones por estado, tendencia, desglose de artefactos de
IA, ejecuciones facturables, actividad por profesional), vista "own" de
`AUDIOLOGIST` (solo su propia actividad, sin `patients` ni
`professional_activity`), rechazo con 403 de `VIEWER`, y el parámetro
`period_days` (efecto y límites)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactStatus, AIPipelineRun, AIPipelineRunStatus
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIPipelineRunRepository
from app.clinical_sessions.domain.entities import ClinicalSessionStatus
from tests.factories import (
    ClinicWithUsers,
    create_ai_artifact_with_version,
    create_clinical_session,
    create_patient,
    dev_headers,
)


async def _create_billable_pipeline_run(
    session: AsyncSession, clinical_session_id: uuid.UUID, triggered_by: uuid.UUID
) -> None:
    """Ejecución facturable mínima (sin `AIGenerationRun`/`AIArtifact`
    asociados — `AnalyticsService.get_summary` solo necesita
    `AIPipelineRun.is_billable`/`started_at`/`completed_at`, ver
    `list_completed_since_for_clinic`). `create_ai_artifact_with_version`
    NO sirve para esto: crea su `AIPipelineRun` con `is_billable=False`
    por defecto (mismo motivo por el que `test_billing_lifecycle.py`
    define su propio `_create_billable_pipeline_run`)."""
    now = datetime.now(UTC)
    pipeline_run = AIPipelineRun(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        triggered_by=triggered_by,
        status=AIPipelineRunStatus.COMPLETED,
        started_at=now,
        completed_at=now,
        request_id=None,
        is_billable=True,
    )
    await SqlAlchemyAIPipelineRunRepository().add(session, pipeline_run)
    await session.commit()


async def test_clinic_summary_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/analytics/clinic-summary")

    assert response.status_code == 401


async def test_viewer_role_is_rejected_with_403(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    response = await api_client.get(
        "/api/v1/analytics/clinic-summary", headers=dev_headers(clinic_with_users.viewer)
    )

    assert response.status_code == 403


async def test_admin_sees_full_clinic_scope(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    clinic = clinic_with_users.clinic
    admin = clinic_with_users.admin
    audiologist = clinic_with_users.audiologist
    patient_admin = await create_patient(db_session, clinic.id, admin.id)
    patient_audiologist = await create_patient(db_session, clinic.id, admin.id)

    session_admin = await create_clinical_session(
        db_session,
        clinic.id,
        patient_admin.id,
        admin.id,
        admin.id,
        status=ClinicalSessionStatus.COMPLETED,
    )
    session_audiologist = await create_clinical_session(
        db_session,
        clinic.id,
        patient_audiologist.id,
        audiologist.id,
        admin.id,
        status=ClinicalSessionStatus.REVIEW_PENDING,
    )
    await create_ai_artifact_with_version(
        db_session, clinic.id, session_admin.id, admin.id, status=AIArtifactStatus.APPROVED
    )
    await create_ai_artifact_with_version(
        db_session,
        clinic.id,
        session_audiologist.id,
        audiologist.id,
        status=AIArtifactStatus.REVIEW_PENDING,
    )
    await _create_billable_pipeline_run(db_session, session_admin.id, admin.id)

    response = await api_client.get("/api/v1/analytics/clinic-summary", headers=dev_headers(admin))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "clinic"
    assert body["period_days"] == 30
    assert body["patients"] == {"total": 2, "new_in_period": 2}
    assert body["sessions_total_in_period"] == 2
    assert body["sessions_by_status"]["completed"] == 1
    assert body["sessions_by_status"]["review_pending"] == 1
    assert body["ai_artifacts_by_status"]["approved"] == 1
    assert body["ai_artifacts_by_status"]["review_pending"] == 1
    assert body["ai_billable_runs_in_period"] == 1
    assert body["professional_activity"] is not None
    activity_by_id = {
        entry["professional_id"]: entry["sessions_in_period"]
        for entry in body["professional_activity"]
    }
    assert activity_by_id[str(admin.id)] == 1
    assert activity_by_id[str(audiologist.id)] == 1


async def test_audiologist_sees_only_own_activity(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    clinic = clinic_with_users.clinic
    admin = clinic_with_users.admin
    audiologist = clinic_with_users.audiologist
    patient_admin = await create_patient(db_session, clinic.id, admin.id)
    patient_audiologist = await create_patient(db_session, clinic.id, admin.id)

    await create_clinical_session(db_session, clinic.id, patient_admin.id, admin.id, admin.id)
    own_session = await create_clinical_session(
        db_session, clinic.id, patient_audiologist.id, audiologist.id, admin.id
    )
    await create_ai_artifact_with_version(db_session, clinic.id, own_session.id, audiologist.id)
    await _create_billable_pipeline_run(db_session, own_session.id, audiologist.id)

    response = await api_client.get(
        "/api/v1/analytics/clinic-summary", headers=dev_headers(audiologist)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "own"
    assert body["patients"] is None
    assert body["professional_activity"] is None
    assert body["sessions_total_in_period"] == 1
    assert body["ai_billable_runs_in_period"] == 1


async def test_period_days_bounds_are_enforced(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
) -> None:
    headers = dev_headers(clinic_with_users.admin)

    too_low = await api_client.get(
        "/api/v1/analytics/clinic-summary", params={"period_days": 0}, headers=headers
    )
    too_high = await api_client.get(
        "/api/v1/analytics/clinic-summary", params={"period_days": 366}, headers=headers
    )
    valid = await api_client.get(
        "/api/v1/analytics/clinic-summary", params={"period_days": 7}, headers=headers
    )

    assert too_low.status_code == 422
    assert too_high.status_code == 422
    assert valid.status_code == 200, valid.text
    assert valid.json()["period_days"] == 7
