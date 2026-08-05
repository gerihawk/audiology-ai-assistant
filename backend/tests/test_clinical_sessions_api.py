"""Tests de integración de /api/v1/clinical-sessions contra Postgres real."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.patients.domain.entities import Patient
from app.users.domain.entities import Role
from tests.factories import ClinicWithUsers, create_clinic_with_users, create_patient, dev_headers


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
        "session_type": "other",
    } | overrides
    response = await api_client.post("/api/v1/clinical-sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_cancelled_session(
    api_client: AsyncClient, headers: dict[str, str], patient_id: str, professional_id: str
) -> dict:
    """`cancelled` no es un estado inicial válido: se crea `scheduled` y se cancela."""
    created = await _create_session(
        api_client, headers, patient_id, professional_id, status="scheduled"
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/cancel", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Creación: estados iniciales válidos e inválidos ------------------------


async def test_create_directly_in_scheduled(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    body = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
        status="scheduled",
    )
    assert body["status"] == "scheduled"
    assert body["started_at"] is None
    assert body["ended_at"] is None


async def test_create_directly_in_progress_sets_started_at(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    body = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
        status="in_progress",
    )
    assert body["status"] == "in_progress"
    assert body["started_at"] is not None
    assert body["ended_at"] is None


async def test_create_directly_completed_sets_started_and_ended_at(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    body = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
        status="completed",
    )
    assert body["status"] == "completed"
    assert body["started_at"] is not None
    assert body["ended_at"] is not None


@pytest.mark.parametrize("initial_status", ["review_pending", "reviewed", "cancelled"])
async def test_create_rejects_non_creatable_initial_status(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    initial_status: str,
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
            "status": initial_status,
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


# --- Validaciones de paciente y profesional ----------------------------------


async def test_create_rejects_archived_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    archived_patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id, is_archived=True
    )
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(archived_patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 409


async def test_create_rejects_nonexistent_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(uuid.uuid4()),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


async def test_create_rejects_inactive_professional(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    from tests.factories import create_user

    inactive = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST, is_active=False
    )
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(inactive.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 409


async def test_create_rejects_viewer_as_professional(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.viewer.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 409


async def test_create_rejects_professional_from_other_clinic(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    other_clinic = await create_clinic_with_users(db_session)
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(other_clinic.admin.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


async def test_audiologist_can_only_create_for_self(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.audiologist),
    )
    assert response.status_code == 403


async def test_viewer_cannot_create(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.viewer.id),
            "session_type": "other",
        },
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert response.status_code == 403


async def test_create_rejects_unknown_field(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
            "diagnosis": "no permitido",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "clinic_id",
        "id",
        "created_by",
        "created_at",
        "started_at",
        "ended_at",
        "reviewed_by",
        "reviewed_at",
    ],
)
async def test_create_rejects_server_managed_fields(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient, field: str
):
    payload = {
        "patient_id": str(patient.id),
        "professional_id": str(clinic_with_users.admin.id),
        "session_type": "other",
        field: str(uuid.uuid4()),
    }
    response = await api_client.post(
        "/api/v1/clinical-sessions", json=payload, headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 422


# --- Transiciones de estado --------------------------------------------------


async def test_full_happy_path_flow(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    session_id = created["id"]

    started = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/start", headers=headers
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    completed = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/complete", headers=headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["ended_at"] is not None

    submitted = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/submit-review", headers=headers
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "review_pending"

    reviewed = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/review", headers=headers
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert reviewed.json()["reviewed_by"] == str(clinic_with_users.admin.id)
    assert reviewed.json()["reviewed_at"] is not None


async def test_start_conflict_from_completed(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="completed"
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/start", headers=headers
    )
    assert response.status_code == 409


async def test_cancel_from_scheduled_and_in_progress(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)

    scheduled = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="scheduled"
    )
    cancel_scheduled = await api_client.post(
        f"/api/v1/clinical-sessions/{scheduled['id']}/cancel", headers=headers
    )
    assert cancel_scheduled.status_code == 200
    assert cancel_scheduled.json()["status"] == "cancelled"

    in_progress = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="in_progress"
    )
    cancel_in_progress = await api_client.post(
        f"/api/v1/clinical-sessions/{in_progress['id']}/cancel", headers=headers
    )
    assert cancel_in_progress.status_code == 200
    assert cancel_in_progress.json()["status"] == "cancelled"


async def test_cancel_conflict_from_completed(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="completed"
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/cancel", headers=headers
    )
    assert response.status_code == 409


async def test_audiologist_cannot_review(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers_admin = dev_headers(clinic_with_users.admin)
    headers_audiologist = dev_headers(clinic_with_users.audiologist)
    created = await _create_session(
        api_client,
        headers_audiologist,
        str(patient.id),
        str(clinic_with_users.audiologist.id),
        status="completed",
    )
    await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/submit-review", headers=headers_audiologist
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/review", headers=headers_audiologist
    )
    assert response.status_code == 403

    # admin sí puede revisarla aunque no sea el profesional responsable
    admin_response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/review", headers=headers_admin
    )
    assert admin_response.status_code == 200


# --- Idempotencia -------------------------------------------------------------


async def test_idempotent_start_preserves_started_at_and_does_not_duplicate_audit(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    session_id = created["id"]

    first = await api_client.post(f"/api/v1/clinical-sessions/{session_id}/start", headers=headers)
    second = await api_client.post(f"/api/v1/clinical-sessions/{session_id}/start", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["started_at"] == second.json()["started_at"]

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.entity_id == uuid.UUID(session_id),
            AuditLogORM.action == "clinical_session.status_changed",
        )
    )
    status_changed_entries = result.scalars().all()
    assert len(status_changed_entries) == 1


# --- Archivado ------------------------------------------------------------


@pytest.mark.parametrize("initial_status", ["completed", "cancelled"])
async def test_archive_allowed_from_completed_and_cancelled(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    initial_status: str,
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="scheduled"
    )
    if initial_status == "completed":
        await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/start", headers=headers)
        await api_client.post(
            f"/api/v1/clinical-sessions/{created['id']}/complete", headers=headers
        )
    else:
        await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/cancel", headers=headers)

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["is_archived"] is True


async def test_archive_allowed_from_reviewed(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="completed"
    )
    await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/submit-review", headers=headers
    )
    await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/review", headers=headers)

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers
    )
    assert response.status_code == 200


async def test_archive_blocked_from_review_pending(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="completed"
    )
    await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/submit-review", headers=headers
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers
    )
    assert response.status_code == 409


@pytest.mark.parametrize("status", ["scheduled", "in_progress"])
async def test_archive_blocked_from_active_states(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient, status: str
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status=status
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers
    )
    assert response.status_code == 409


async def test_restore_preserves_previous_status(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_cancelled_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers)

    restored = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/restore", headers=headers
    )
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False
    assert restored.json()["status"] == "cancelled"


async def test_audiologist_cannot_restore(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers_admin = dev_headers(clinic_with_users.admin)
    headers_audiologist = dev_headers(clinic_with_users.audiologist)
    created = await _create_cancelled_session(
        api_client,
        headers_audiologist,
        str(patient.id),
        str(clinic_with_users.audiologist.id),
    )
    await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers_audiologist
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/restore", headers=headers_audiologist
    )
    assert response.status_code == 403

    admin_response = await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/restore", headers=headers_admin
    )
    assert admin_response.status_code == 200


# --- Reglas de edición por estado --------------------------------------------


async def test_update_restricted_to_title_and_notes_in_review_pending(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="completed"
    )
    await api_client.post(
        f"/api/v1/clinical-sessions/{created['id']}/submit-review", headers=headers
    )

    allowed = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"title": "Nuevo título"},
        headers=headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Nuevo título"

    disallowed = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"session_type": "review"},
        headers=headers,
    )
    assert disallowed.status_code == 409


async def test_update_blocked_when_reviewed_or_cancelled(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)

    cancelled = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="scheduled"
    )
    await api_client.post(f"/api/v1/clinical-sessions/{cancelled['id']}/cancel", headers=headers)
    response = await api_client.patch(
        f"/api/v1/clinical-sessions/{cancelled['id']}", json={"title": "x"}, headers=headers
    )
    assert response.status_code == 409


async def test_update_blocked_when_archived(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_cancelled_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers)

    response = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}", json={"title": "x"}, headers=headers
    )
    assert response.status_code == 409


async def test_change_professional_admin_only(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers_admin = dev_headers(clinic_with_users.admin)
    headers_audiologist = dev_headers(clinic_with_users.audiologist)
    created = await _create_session(
        api_client, headers_admin, str(patient.id), str(clinic_with_users.admin.id)
    )

    forbidden = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"professional_id": str(clinic_with_users.audiologist.id)},
        headers=headers_audiologist,
    )
    assert forbidden.status_code == 403

    allowed = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"professional_id": str(clinic_with_users.audiologist.id)},
        headers=headers_admin,
    )
    assert allowed.status_code == 200
    assert allowed.json()["professional_id"] == str(clinic_with_users.audiologist.id)


async def test_reviewed_by_and_reviewed_at_rejected_from_client(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "other",
            "reviewed_by": str(clinic_with_users.admin.id),
        },
        headers=headers,
    )
    assert response.status_code == 422

    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    patch_response = await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"reviewed_at": "2026-01-01T00:00:00Z"},
        headers=headers,
    )
    assert patch_response.status_code == 422


# --- Aislamiento por clínica --------------------------------------------------


async def test_session_from_other_clinic_returns_404(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    other_clinic = await create_clinic_with_users(db_session)
    created = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
    )

    response = await api_client.get(
        f"/api/v1/clinical-sessions/{created['id']}", headers=dev_headers(other_clinic.admin)
    )
    assert response.status_code == 404


# --- Auditoría ----------------------------------------------------------------


async def test_create_writes_audit_with_initial_status(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="in_progress"
    )

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.entity_id == uuid.UUID(created["id"]),
            AuditLogORM.action == "clinical_session.created",
        )
    )
    entry = result.scalar_one()
    assert entry.audit_metadata == {"initial_status": "in_progress"}
    assert entry.entity_type == "clinical_session"


async def test_professional_change_audit_has_uuids_never_field_values(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    secret_title = "titulo-administrativo-sensible-de-prueba"
    await api_client.patch(
        f"/api/v1/clinical-sessions/{created['id']}",
        json={"professional_id": str(clinic_with_users.audiologist.id), "title": secret_title},
        headers=headers,
    )

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.entity_id == uuid.UUID(created["id"]))
    )
    entries = {row.action: row for row in result.scalars().all()}

    professional_changed = entries["clinical_session.professional_changed"]
    assert professional_changed.audit_metadata == {
        "previous_professional_id": str(clinic_with_users.admin.id),
        "new_professional_id": str(clinic_with_users.audiologist.id),
    }

    updated_entry = entries["clinical_session.updated"]
    assert updated_entry.audit_metadata == {"changed_fields": ["title"]}
    assert secret_title not in str(updated_entry.audit_metadata)


async def test_cancel_writes_its_own_action_not_status_changed(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id), status="scheduled"
    )
    await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/cancel", headers=headers)

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.entity_id == uuid.UUID(created["id"]))
    )
    actions = {row.action for row in result.scalars().all()}
    assert "clinical_session.cancelled" in actions
    assert "clinical_session.status_changed" not in actions


# --- Listado y filtros --------------------------------------------------------


async def test_list_filters_by_status_and_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    headers = dev_headers(clinic_with_users.admin)
    patient_a = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    patient_b = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )

    await _create_session(
        api_client, headers, str(patient_a.id), str(clinic_with_users.admin.id), status="scheduled"
    )
    await _create_session(
        api_client, headers, str(patient_b.id), str(clinic_with_users.admin.id), status="completed"
    )

    by_patient = await api_client.get(
        f"/api/v1/clinical-sessions?patient_id={patient_a.id}", headers=headers
    )
    assert by_patient.json()["total"] == 1

    by_status = await api_client.get("/api/v1/clinical-sessions?status=completed", headers=headers)
    assert all(item["status"] == "completed" for item in by_status.json()["items"])


async def test_list_excludes_archived_by_default(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_cancelled_session(
        api_client, headers, str(patient.id), str(clinic_with_users.admin.id)
    )
    await api_client.post(f"/api/v1/clinical-sessions/{created['id']}/archive", headers=headers)

    default_listing = await api_client.get(
        f"/api/v1/clinical-sessions?patient_id={patient.id}", headers=headers
    )
    with_archived = await api_client.get(
        f"/api/v1/clinical-sessions?patient_id={patient.id}&include_archived=true", headers=headers
    )
    assert default_listing.json()["total"] == 0
    assert with_archived.json()["total"] == 1


async def test_list_filters_by_scheduled_date_range(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    import datetime as dt

    headers = dev_headers(clinic_with_users.admin)
    near_future = (dt.datetime.now(dt.UTC) + dt.timedelta(days=2)).isoformat()
    far_future = (dt.datetime.now(dt.UTC) + dt.timedelta(days=30)).isoformat()

    await _create_session(
        api_client,
        headers,
        str(patient.id),
        str(clinic_with_users.admin.id),
        scheduled_at=near_future,
    )
    await _create_session(
        api_client,
        headers,
        str(patient.id),
        str(clinic_with_users.admin.id),
        scheduled_at=far_future,
    )

    today = dt.date.today().isoformat()
    one_week = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    response = await api_client.get(
        f"/api/v1/clinical-sessions?scheduled_from={today}&scheduled_to={one_week}", headers=headers
    )
    assert response.json()["total"] == 1


async def test_list_pagination_is_stable(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    for _ in range(3):
        await _create_session(api_client, headers, str(patient.id), str(clinic_with_users.admin.id))

    first_page = await api_client.get(
        f"/api/v1/clinical-sessions?patient_id={patient.id}&limit=2&offset=0", headers=headers
    )
    second_page = await api_client.get(
        f"/api/v1/clinical-sessions?patient_id={patient.id}&limit=2&offset=2", headers=headers
    )
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    first_ids = {item["id"] for item in first_page.json()["items"]}
    second_ids = {item["id"] for item in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)


# --- Transaccionalidad --------------------------------------------------------


async def test_create_rolls_back_session_if_audit_write_fails(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    from app.clinical_sessions.domain.entities import ClinicalSessionStatus, SessionType
    from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
    from app.clinical_sessions.service import ClinicalSessionCreateData, ClinicalSessionService
    from tests.factories import current_user_from

    class _BrokenAuditRepository:
        async def add(self, session, entry):  # noqa: ARG002
            raise RuntimeError("fallo simulado de auditoría")

    service = ClinicalSessionService(db_session, audit_repository=_BrokenAuditRepository())
    current_user = current_user_from(clinic_with_users.admin)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        await service.create(
            current_user,
            ClinicalSessionCreateData(
                patient_id=patient.id,
                professional_id=clinic_with_users.admin.id,
                session_type=SessionType.OTHER,
                status=ClinicalSessionStatus.SCHEDULED,
                scheduled_at=None,
                title="No debería persistir",
                administrative_notes=None,
            ),
            "req-rollback-test",
        )

    items, total = await SqlAlchemyClinicalSessionRepository().list(
        db_session,
        clinic_with_users.clinic.id,
        patient_id=patient.id,
        professional_id=None,
        status=None,
        session_type=None,
        scheduled_from=None,
        scheduled_to=None,
        search=None,
        include_archived=True,
        limit=10,
        offset=0,
    )
    assert total == 0
    assert items == []
