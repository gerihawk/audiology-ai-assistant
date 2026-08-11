"""Edición humana (HUMAN_EDITED) y soft-delete auditado de AIArtifact —
precondiciones del hito 6.0 de la Fase 6 (docs/fase-6-rfc.md §9.1)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, create_clinic_with_users, create_patient, dev_headers


async def _create_session(
    api_client: AsyncClient, headers: dict[str, str], patient_id: str, professional_id: str
) -> dict:
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": patient_id,
            "professional_id": professional_id,
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


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


async def _run_pipeline_and_get_first_artifact(
    api_client: AsyncClient, headers: dict[str, str], session_id: str
) -> dict:
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline", headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["artifacts"][0]


# --- Edición humana -----------------------------------------------------------


async def test_edit_content_creates_human_edited_version_and_reopens_review(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )
    await api_client.post(f"/api/v1/ai-artifacts/{artifact['id']}/approve", headers=headers)

    response = await api_client.patch(
        f"/api/v1/ai-artifacts/{artifact['id']}/content",
        json={
            "content": {"text": "texto corregido por el profesional"},
            "change_note": "corrección",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version_number"] == 2
    assert body["content"] == {"text": "texto corregido por el profesional"}
    assert body["status"] == "review_pending"
    assert body["approved_by"] is None
    assert body["approved_at"] is None


async def test_edit_content_persists_source_human_edited_in_version_history(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )

    await api_client.patch(
        f"/api/v1/ai-artifacts/{artifact['id']}/content",
        json={"content": {"text": "editado"}, "change_note": None},
        headers=headers,
    )
    response = await api_client.get(
        f"/api/v1/ai-artifacts/{artifact['id']}/versions", headers=headers
    )

    versions = response.json()["items"]
    current = next(v for v in versions if v["is_current"])
    assert current["source"] == "human_edited"


async def test_edit_content_writes_audit_log_entry(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )

    await api_client.patch(
        f"/api/v1/ai-artifacts/{artifact['id']}/content",
        json={"content": {"text": "editado"}, "change_note": None},
        headers=headers,
    )

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.action == "ai_artifact.human_edited",
            AuditLogORM.entity_id == uuid.UUID(artifact["id"]),
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].actor_user_id == clinic_with_users.admin.id


async def test_edit_nonexistent_artifact_returns_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.patch(
        f"/api/v1/ai-artifacts/{uuid.uuid4()}/content",
        json={"content": {"text": "x"}, "change_note": None},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


async def test_viewer_cannot_edit_content(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    admin_headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, admin_headers, clinical_session["id"]
    )

    response = await api_client.patch(
        f"/api/v1/ai-artifacts/{artifact['id']}/content",
        json={"content": {"text": "x"}, "change_note": None},
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert response.status_code == 403


async def test_audiologist_cannot_edit_artifact_of_others_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    admin_headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, admin_headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    artifact = await _run_pipeline_and_get_first_artifact(api_client, admin_headers, session["id"])

    response = await api_client.patch(
        f"/api/v1/ai-artifacts/{artifact['id']}/content",
        json={"content": {"text": "x"}, "change_note": None},
        headers=dev_headers(clinic_with_users.audiologist),
    )
    assert response.status_code == 403


# --- Soft-delete ---------------------------------------------------------------


async def test_delete_artifact_excludes_it_from_listing_and_read(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )

    delete_response = await api_client.delete(
        f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers
    )
    assert delete_response.status_code == 204

    get_response = await api_client.get(f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers)
    assert get_response.status_code == 404

    list_response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/artifacts", headers=headers
    )
    remaining_ids = {a["id"] for a in list_response.json()["items"]}
    assert artifact["id"] not in remaining_ids


async def test_delete_artifact_is_idempotent(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )

    first = await api_client.delete(f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers)
    second = await api_client.delete(f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers)

    assert first.status_code == 204
    assert second.status_code == 204


async def test_delete_artifact_writes_audit_log_entry(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, headers, clinical_session["id"]
    )

    await api_client.delete(f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers)

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.action == "ai_artifact.deleted",
            AuditLogORM.entity_id == uuid.UUID(artifact["id"]),
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].actor_user_id == clinic_with_users.admin.id


async def test_delete_nonexistent_artifact_returns_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.delete(
        f"/api/v1/ai-artifacts/{uuid.uuid4()}", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 404


async def test_viewer_cannot_delete_artifact(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    admin_headers = dev_headers(clinic_with_users.admin)
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, admin_headers, clinical_session["id"]
    )

    response = await api_client.delete(
        f"/api/v1/ai-artifacts/{artifact['id']}", headers=dev_headers(clinic_with_users.viewer)
    )
    assert response.status_code == 403


async def test_delete_cross_clinic_returns_404(api_client: AsyncClient, db_session: AsyncSession):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)
    session = await _create_session(
        api_client, dev_headers(clinic_a.admin), str(patient_a.id), str(clinic_a.audiologist.id)
    )
    artifact = await _run_pipeline_and_get_first_artifact(
        api_client, dev_headers(clinic_a.admin), session["id"]
    )

    response = await api_client.delete(
        f"/api/v1/ai-artifacts/{artifact['id']}", headers=dev_headers(clinic_b.admin)
    )
    assert response.status_code == 404
