"""Tests de integración del AI Pipeline (Fase 4.1) contra Postgres real."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIGenerationRunStatus,
    AIPipelineRun,
    AIPipelineRunStatus,
)
from app.ai_pipeline.domain.safety import FORBIDDEN_CLINICAL_LANGUAGE
from app.ai_pipeline.infrastructure.orm import (
    AIArtifactORM,
    AIArtifactVersionORM,
    AIGenerationRunORM,
    AIPipelineRunORM,
)
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.ai_pipeline.service import AIPipelineService
from app.audit_log.infrastructure.orm import AuditLogORM
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, create_clinic_with_users, create_patient, dev_headers

_ALL_ARTIFACT_TYPES = {
    "transcript",
    "summary",
    "patient_summary",
    "clinical_flags",
    "missing_information",
    "anamnesis",
}


async def _create_session(
    api_client: AsyncClient,
    headers: dict[str, str],
    patient_id: str,
    professional_id: str,
    **overrides,
) -> dict:
    payload = {
        "patient_id": patient_id,
        "professional_id": professional_id,
        "session_type": "initial_assessment",
        "status": "completed",
    } | overrides
    response = await api_client.post("/api/v1/clinical-sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _run_pipeline(
    api_client: AsyncClient, headers: dict[str, str], session_id: str
) -> tuple[int, dict]:
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline", headers=headers
    )
    return response.status_code, response.json()


@pytest.fixture
async def clinical_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
) -> dict:
    return await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.audiologist.id),
    )


# --- Creación de PipelineRun y ejecución completa ---------------------------


async def test_run_pipeline_creates_all_five_artifacts(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    assert status_code == 201, body
    assert body["status"] == "completed"
    artifact_types = {a["artifact_type"] for a in body["artifacts"]}
    assert artifact_types == _ALL_ARTIFACT_TYPES
    assert len(body["step_outcomes"]) == 6
    assert all(o["status"] == "completed" for o in body["step_outcomes"])


async def test_run_pipeline_artifacts_are_review_pending_with_confidence_and_provider(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    for artifact in body["artifacts"]:
        assert artifact["status"] == "review_pending"
        assert artifact["version_number"] == 1
        assert artifact["confidence"] is not None
        assert 0 <= artifact["confidence"] <= 100
        assert artifact["provider_name"] == "mock"
        assert artifact["content"] is not None
        assert artifact["created_at"] is not None
        assert artifact["updated_at"] is not None
        assert "Contenido generado mediante IA" in artifact["ai_disclaimer"]


async def test_run_pipeline_anamnesis_never_marks_informado_without_evidence(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )
    anamnesis = next(a for a in body["artifacts"] if a["artifact_type"] == "anamnesis")

    for field_name, field in anamnesis["content"].items():
        if field["status"] in ("informado", "negado_explicitamente"):
            assert field["value"], f"{field_name} marcado {field['status']} sin evidencia"


async def test_run_pipeline_rejects_forbidden_and_diagnostic_language(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    """No garantiza semántica clínica real (son mocks), pero sí que ningún
    texto generado usa las expresiones explícitamente prohibidas."""
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    for artifact in body["artifacts"]:
        rendered = str(artifact["content"]).lower()
        for phrase in FORBIDDEN_CLINICAL_LANGUAGE:
            assert phrase not in rendered


# --- Persistencia y auditoría ------------------------------------------------


async def test_run_pipeline_persists_generation_runs_with_audit_fields(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    result = await db_session.execute(
        select(AIGenerationRunORM).where(
            AIGenerationRunORM.ai_pipeline_run_id == uuid.UUID(body["pipeline_run_id"])
        )
    )
    runs = result.scalars().all()
    assert len(runs) == 6
    for run in runs:
        assert run.status == AIGenerationRunStatus.COMPLETED.value
        assert run.provider_name == "mock"
        assert run.latency_ms is not None
        assert run.execution_time_ms is not None
        assert run.input_token_count is not None
        assert run.output_token_count is not None
        assert run.estimated_cost_usd == Decimal("0")
        assert run.resulting_version_number == 1
        # Nunca se guarda el prompt renderizado salvo activación explícita
        # (ai_store_rendered_prompts=false por defecto) — ver
        # docs/ai-pipeline-architecture.md §7.5.
        assert run.rendered_system_prompt is None
        assert run.rendered_user_prompt is None


async def test_run_pipeline_writes_audit_log_entry(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.action == "ai_pipeline.triggered",
            AuditLogORM.entity_id == uuid.UUID(body["pipeline_run_id"]),
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].actor_user_id == clinic_with_users.admin.id
    # Nunca contenido clínico, solo nombres de tipo y estado (ver
    # docs/ai-pipeline-architecture.md §8).
    outcomes_metadata = entries[0].audit_metadata["outcomes"]
    assert set(outcomes_metadata.keys()) == _ALL_ARTIFACT_TYPES
    assert all(v == "completed" for v in outcomes_metadata.values())


async def test_pipeline_run_persisted_with_completed_status(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    result = await db_session.execute(
        select(AIPipelineRunORM).where(AIPipelineRunORM.id == uuid.UUID(body["pipeline_run_id"]))
    )
    row = result.scalar_one()
    assert row.status == AIPipelineRunStatus.COMPLETED.value
    assert row.completed_at is not None
    assert row.triggered_by == clinic_with_users.admin.id


# --- Historial de versiones ---------------------------------------------------


async def test_list_versions_returns_all_versions_most_recent_first(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, first = await _run_pipeline(api_client, headers, clinical_session["id"])
    await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = next(a["id"] for a in first["artifacts"] if a["artifact_type"] == "transcript")

    response = await api_client.get(f"/api/v1/ai-artifacts/{artifact_id}/versions", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [v["version_number"] for v in items] == [2, 1]
    assert items[0]["is_current"] is True
    assert items[1]["is_current"] is False
    assert items[0]["content"] != {} and items[1]["content"] != {}
    assert items[0]["provider_name"] == "mock"


async def test_list_versions_for_nonexistent_artifact_returns_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.get(
        f"/api/v1/ai-artifacts/{uuid.uuid4()}/versions",
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


async def test_list_versions_cross_clinic_returns_404(
    api_client: AsyncClient, db_session: AsyncSession
):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)
    session = await _create_session(
        api_client, dev_headers(clinic_a.admin), str(patient_a.id), str(clinic_a.audiologist.id)
    )
    _, body = await _run_pipeline(api_client, dev_headers(clinic_a.admin), session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.get(
        f"/api/v1/ai-artifacts/{artifact_id}/versions", headers=dev_headers(clinic_b.admin)
    )
    assert response.status_code == 404


async def test_viewer_can_list_versions(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    _, body = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.get(
        f"/api/v1/ai-artifacts/{artifact_id}/versions",
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


# --- Versionado y reejecución -------------------------------------------------


async def test_rerunning_pipeline_creates_new_versions_without_deleting_previous(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    _, first = await _run_pipeline(api_client, headers, clinical_session["id"])
    status_code, second = await _run_pipeline(api_client, headers, clinical_session["id"])

    assert status_code == 201
    for artifact in second["artifacts"]:
        assert artifact["version_number"] == 2

    # Sigue habiendo exactamente 5 AIArtifact (no se duplican), pero 10
    # AIArtifactVersion (nada se sobrescribe ni se borra).
    artifacts_result = await db_session.execute(
        select(AIArtifactORM).where(
            AIArtifactORM.clinical_session_id == uuid.UUID(clinical_session["id"])
        )
    )
    assert len(artifacts_result.scalars().all()) == 6

    first_transcript_id = next(
        a["id"] for a in first["artifacts"] if a["artifact_type"] == "transcript"
    )
    versions_result = await db_session.execute(
        select(AIArtifactVersionORM).where(
            AIArtifactVersionORM.ai_artifact_id == uuid.UUID(first_transcript_id)
        )
    )
    versions = versions_result.scalars().all()
    assert len(versions) == 2
    assert {v.version_number for v in versions} == {1, 2}


async def test_rerunning_pipeline_reopens_approved_artifact_for_review(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, first = await _run_pipeline(api_client, headers, clinical_session["id"])
    transcript_id = next(a["id"] for a in first["artifacts"] if a["artifact_type"] == "transcript")

    approve_response = await api_client.post(
        f"/api/v1/ai-artifacts/{transcript_id}/approve", headers=headers
    )
    assert approve_response.json()["status"] == "approved"

    _, second = await _run_pipeline(api_client, headers, clinical_session["id"])
    transcript_v2 = next(a for a in second["artifacts"] if a["artifact_type"] == "transcript")
    assert transcript_v2["status"] == "review_pending"
    assert transcript_v2["approved_by"] is None
    assert transcript_v2["approved_at"] is None


# --- Aprobación y rechazo -----------------------------------------------------


async def test_approve_artifact(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, body = await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/approve", headers=headers)

    assert response.status_code == 200
    approved = response.json()
    assert approved["status"] == "approved"
    assert approved["approved_by"] == str(clinic_with_users.admin.id)
    assert approved["approved_at"] is not None


async def test_reject_artifact_with_reason(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, body = await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.post(
        f"/api/v1/ai-artifacts/{artifact_id}/reject",
        headers=headers,
        json={"rejection_reason": "Contenido insuficiente"},
    )

    assert response.status_code == 200
    rejected = response.json()
    assert rejected["status"] == "rejected"
    assert rejected["rejected_by"] == str(clinic_with_users.admin.id)
    assert rejected["rejection_reason"] == "Contenido insuficiente"


async def test_reject_artifact_without_body(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, body = await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/reject", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["rejection_reason"] is None


async def test_approve_is_idempotent_no_duplicate_audit(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    _, body = await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = body["artifacts"][0]["id"]

    first = await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/approve", headers=headers)
    second = await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/approve", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["approved_at"] == second.json()["approved_at"]

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.action == "ai_artifact.approved",
            AuditLogORM.entity_id == uuid.UUID(artifact_id),
        )
    )
    assert len(result.scalars().all()) == 1


async def test_approve_rejected_artifact_requires_review_pending_first(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, body = await _run_pipeline(api_client, headers, clinical_session["id"])
    artifact_id = body["artifacts"][0]["id"]

    await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/reject", headers=headers)
    response = await api_client.post(f"/api/v1/ai-artifacts/{artifact_id}/approve", headers=headers)

    assert response.status_code == 409


async def test_approve_nonexistent_artifact_returns_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.post(
        f"/api/v1/ai-artifacts/{uuid.uuid4()}/approve", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 404


# --- Permisos por rol y propiedad --------------------------------------------


async def test_viewer_cannot_trigger_pipeline(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, _ = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.viewer), clinical_session["id"]
    )
    assert status_code == 403


async def test_viewer_can_read_artifacts(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    await _run_pipeline(api_client, dev_headers(clinic_with_users.admin), clinical_session["id"])

    response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/artifacts",
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 6


async def test_audiologist_can_trigger_pipeline_on_own_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.audiologist.id),
    )
    status_code, _ = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.audiologist), session["id"]
    )
    assert status_code == 201


async def test_audiologist_cannot_trigger_pipeline_on_others_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    # profesional responsable = admin (rol válido para ser professional_id),
    # pero quien intenta disparar es el audiologist ficticio, ajeno a la sesión.
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
    )
    status_code, _ = await _run_pipeline(
        api_client, dev_headers(clinic_with_users.audiologist), session["id"]
    )
    assert status_code == 403


async def test_audiologist_cannot_approve_artifact_of_others_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
    )
    _, body = await _run_pipeline(api_client, dev_headers(clinic_with_users.admin), session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.post(
        f"/api/v1/ai-artifacts/{artifact_id}/approve",
        headers=dev_headers(clinic_with_users.audiologist),
    )
    assert response.status_code == 403


# --- Concurrencia -------------------------------------------------------------


async def test_second_trigger_while_processing_is_rejected(
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    """Simula una ejecución en curso insertando directamente un
    ai_pipeline_runs en `processing`, sin pasar por el orquestador
    síncrono (que en este MVP nunca deja ese estado observable entre
    peticiones) — ver docs/ai-pipeline-architecture.md §8."""
    repo = SqlAlchemyAIPipelineRunRepository()
    now = datetime.now(UTC)
    await repo.add(
        db_session,
        AIPipelineRun(
            id=uuid.uuid4(),
            clinical_session_id=uuid.UUID(clinical_session["id"]),
            triggered_by=clinic_with_users.admin.id,
            status=AIPipelineRunStatus.PROCESSING,
            started_at=now,
            completed_at=None,
            request_id="test-request-id",
        ),
    )
    await db_session.commit()

    service = AIPipelineService(db_session)
    current_user = CurrentUser(
        id=clinic_with_users.admin.id,
        clinic_id=clinic_with_users.clinic.id,
        email=clinic_with_users.admin.email,
        display_name=clinic_with_users.admin.display_name,
        role=clinic_with_users.admin.role,
    )

    with pytest.raises(ConflictError):
        await service.run_pipeline(current_user, uuid.UUID(clinical_session["id"]), "req-2")


# --- Rollback ante fallo de infraestructura -----------------------------------


class _BrokenGenerationRunRepository:
    """Falla en la segunda inserción — simula un error inesperado de
    infraestructura (no un fallo normal de proveedor) a mitad de la
    ejecución del pipeline."""

    def __init__(self) -> None:
        self._calls = 0

    async def add(self, session, run):
        self._calls += 1
        if self._calls == 2:
            raise RuntimeError("fallo de infraestructura simulado")
        return await SqlAlchemyAIGenerationRunRepository().add(session, run)

    async def list_by_pipeline_run(self, session, ai_pipeline_run_id):
        raise NotImplementedError


async def test_infrastructure_failure_rolls_back_entire_pipeline_run(
    clinic_with_users: ClinicWithUsers, clinical_session: dict, db_session: AsyncSession
):
    service = AIPipelineService(
        db_session, generation_run_repository=_BrokenGenerationRunRepository()
    )
    current_user = CurrentUser(
        id=clinic_with_users.admin.id,
        clinic_id=clinic_with_users.clinic.id,
        email=clinic_with_users.admin.email,
        display_name=clinic_with_users.admin.display_name,
        role=clinic_with_users.admin.role,
    )

    with pytest.raises(RuntimeError):
        await service.run_pipeline(current_user, uuid.UUID(clinical_session["id"]), "req-rollback")

    # Nada debe haber quedado persistido: ni el pipeline_run, ni ningún
    # artefacto, ni ninguna entrada de auditoría.
    pipeline_runs = await db_session.execute(
        select(AIPipelineRunORM).where(
            AIPipelineRunORM.clinical_session_id == uuid.UUID(clinical_session["id"])
        )
    )
    assert pipeline_runs.scalars().all() == []

    artifacts = await db_session.execute(
        select(AIArtifactORM).where(
            AIArtifactORM.clinical_session_id == uuid.UUID(clinical_session["id"])
        )
    )
    assert artifacts.scalars().all() == []

    audit_entries = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.action == "ai_pipeline.triggered")
    )
    assert audit_entries.scalars().all() == []


# --- Aislamiento entre clínicas -----------------------------------------------


async def test_cross_clinic_session_returns_404(api_client: AsyncClient, db_session: AsyncSession):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)

    session = await _create_session(
        api_client,
        dev_headers(clinic_a.admin),
        str(patient_a.id),
        str(clinic_a.audiologist.id),
    )

    status_code, _ = await _run_pipeline(api_client, dev_headers(clinic_b.admin), session["id"])
    assert status_code == 404


async def test_cross_clinic_artifact_returns_404(api_client: AsyncClient, db_session: AsyncSession):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)

    session = await _create_session(
        api_client,
        dev_headers(clinic_a.admin),
        str(patient_a.id),
        str(clinic_a.audiologist.id),
    )
    _, body = await _run_pipeline(api_client, dev_headers(clinic_a.admin), session["id"])
    artifact_id = body["artifacts"][0]["id"]

    response = await api_client.get(
        f"/api/v1/ai-artifacts/{artifact_id}", headers=dev_headers(clinic_b.admin)
    )
    assert response.status_code == 404

    approve_response = await api_client.post(
        f"/api/v1/ai-artifacts/{artifact_id}/approve", headers=dev_headers(clinic_b.admin)
    )
    assert approve_response.status_code == 404


async def test_cross_clinic_artifact_list_is_empty_not_error(
    api_client: AsyncClient, db_session: AsyncSession
):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_b = await create_patient(db_session, clinic_b.clinic.id, clinic_b.admin.id)

    session_b = await _create_session(
        api_client,
        dev_headers(clinic_b.admin),
        str(patient_b.id),
        str(clinic_b.audiologist.id),
    )

    # Sesión de otra clínica: 404, no una lista vacía silenciosa que
    # pudiera confundirse con "sesión propia sin artefactos".
    response = await api_client.get(
        f"/api/v1/clinical-sessions/{session_b['id']}/artifacts",
        headers=dev_headers(clinic_a.admin),
    )
    assert response.status_code == 404
