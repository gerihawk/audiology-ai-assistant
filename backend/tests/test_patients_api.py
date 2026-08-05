"""Tests de integración de /api/v1/patients contra Postgres real (BD de test aislada)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from tests.factories import ClinicWithUsers, create_clinic_with_users, dev_headers


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload = {"internal_code": f"PAT-{uuid.uuid4().hex[:8].upper()}"} | overrides
    response = await api_client.post("/api/v1/patients", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- Creación y validaciones ---------------------------------------------


async def test_create_patient_succeeds(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    response = await api_client.post(
        "/api/v1/patients",
        json={
            "internal_code": "PAT-0001",
            "display_name": "Paciente de Prueba",
            "birth_year": 1980,
            "sex": "female",
            "notes": "  nota   con   espacios  ",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["internal_code"] == "PAT-0001"
    assert body["clinic_id"] == str(clinic_with_users.clinic.id)
    assert body["is_archived"] is False
    assert body["notes"] == "nota con espacios"  # espacios normalizados
    assert body["created_by"] == str(clinic_with_users.admin.id)
    assert body["schema_version"] == 1


async def test_create_patient_requires_internal_code(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.post(
        "/api/v1/patients", json={}, headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("internal_code", ["", "code with spaces", "código/inválido", " "])
async def test_create_patient_rejects_invalid_internal_code(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, internal_code: str
):
    response = await api_client.post(
        "/api/v1/patients",
        json={"internal_code": internal_code},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("birth_year", [1899, 2999])
async def test_create_patient_rejects_birth_year_out_of_range(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, birth_year: int
):
    response = await api_client.post(
        "/api/v1/patients",
        json={"internal_code": "PAT-BY", "birth_year": birth_year},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_create_patient_rejects_unknown_field(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.post(
        "/api/v1/patients",
        json={"internal_code": "PAT-EXTRA", "diagnosis": "no permitido"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["clinic_id", "created_by", "created_at", "id", "schema_version"])
async def test_create_patient_rejects_protected_fields(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, field: str
):
    payload = {"internal_code": "PAT-PROT", field: str(uuid.uuid4())}
    response = await api_client.post(
        "/api/v1/patients", json=payload, headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 422


# --- Unicidad del código interno ------------------------------------------


async def test_duplicate_internal_code_within_clinic_conflicts(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    await _create_patient(api_client, headers, internal_code="PAT-DUP")

    response = await api_client.post(
        "/api/v1/patients", json={"internal_code": "PAT-DUP"}, headers=headers
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert body["error"]["field"] == "internal_code"


async def test_same_internal_code_allowed_across_different_clinics(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    other_clinic = await create_clinic_with_users(db_session)

    r1 = await api_client.post(
        "/api/v1/patients",
        json={"internal_code": "PAT-SHARED"},
        headers=dev_headers(clinic_with_users.admin),
    )
    r2 = await api_client.post(
        "/api/v1/patients",
        json={"internal_code": "PAT-SHARED"},
        headers=dev_headers(other_clinic.admin),
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


# --- Listado, búsqueda, paginación, archivados ----------------------------


async def test_list_patients_paginated(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    headers = dev_headers(clinic_with_users.admin)
    for i in range(3):
        await _create_patient(api_client, headers, internal_code=f"PAT-PAGE-{i}")

    first_page = await api_client.get("/api/v1/patients?limit=2&offset=0", headers=headers)
    second_page = await api_client.get("/api/v1/patients?limit=2&offset=2", headers=headers)

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    first_ids = {item["id"] for item in first_page.json()["items"]}
    second_ids = {item["id"] for item in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)  # sin solapamiento entre páginas


async def test_search_by_internal_code_and_display_name(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    await _create_patient(api_client, headers, internal_code="ZZZ-0001", display_name="Ana García")
    await _create_patient(api_client, headers, internal_code="ZZZ-0002", display_name="Luis Pérez")

    by_code = await api_client.get("/api/v1/patients?search=ZZZ-0001", headers=headers)
    by_name = await api_client.get("/api/v1/patients?search=garcía", headers=headers)

    assert [p["internal_code"] for p in by_code.json()["items"]] == ["ZZZ-0001"]
    assert [p["internal_code"] for p in by_name.json()["items"]] == ["ZZZ-0001"]


async def test_archived_patients_excluded_by_default_and_included_with_filter(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    patient = await _create_patient(api_client, headers, internal_code="PAT-ARCH")
    await api_client.post(f"/api/v1/patients/{patient['id']}/archive", headers=headers)

    default_listing = await api_client.get("/api/v1/patients", headers=headers)
    with_archived = await api_client.get("/api/v1/patients?include_archived=true", headers=headers)

    default_codes = [p["internal_code"] for p in default_listing.json()["items"]]
    archived_codes = [p["internal_code"] for p in with_archived.json()["items"]]
    assert "PAT-ARCH" not in default_codes
    assert "PAT-ARCH" in archived_codes


# --- Obtención, actualización -----------------------------------------------


async def test_get_patient_by_id(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)

    response = await api_client.get(f"/api/v1/patients/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_nonexistent_patient_returns_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.get(
        f"/api/v1/patients/{uuid.uuid4()}", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_update_patient_changes_fields(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers, display_name="Nombre Original")

    response = await api_client.patch(
        f"/api/v1/patients/{created['id']}",
        json={"display_name": "Nombre Actualizado"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Nombre Actualizado"
    assert body["updated_by"] == str(clinic_with_users.admin.id)


async def test_update_archived_patient_conflicts(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)
    await api_client.post(f"/api/v1/patients/{created['id']}/archive", headers=headers)

    response = await api_client.patch(
        f"/api/v1/patients/{created['id']}", json={"notes": "no debería aplicarse"}, headers=headers
    )
    assert response.status_code == 409


# --- Archivar / restaurar ---------------------------------------------------


async def test_archive_then_restore_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)

    archived = await api_client.post(f"/api/v1/patients/{created['id']}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True
    assert archived.json()["archived_at"] is not None

    restored = await api_client.post(f"/api/v1/patients/{created['id']}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False
    assert restored.json()["archived_at"] is None


async def test_archive_is_idempotent(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)

    first = await api_client.post(f"/api/v1/patients/{created['id']}/archive", headers=headers)
    second = await api_client.post(f"/api/v1/patients/{created['id']}/archive", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["archived_at"] is not None


async def test_restore_is_idempotent(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)

    response = await api_client.post(f"/api/v1/patients/{created['id']}/restore", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_archived"] is False


# --- Permisos por rol --------------------------------------------------------


async def test_viewer_cannot_create_update_or_archive(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    admin_headers = dev_headers(clinic_with_users.admin)
    viewer_headers = dev_headers(clinic_with_users.viewer)
    created = await _create_patient(api_client, admin_headers)

    create_resp = await api_client.post(
        "/api/v1/patients", json={"internal_code": "PAT-VIEWER"}, headers=viewer_headers
    )
    update_resp = await api_client.patch(
        f"/api/v1/patients/{created['id']}", json={"notes": "x"}, headers=viewer_headers
    )
    archive_resp = await api_client.post(
        f"/api/v1/patients/{created['id']}/archive", headers=viewer_headers
    )

    assert create_resp.status_code == 403
    assert update_resp.status_code == 403
    assert archive_resp.status_code == 403


async def test_viewer_can_read(api_client: AsyncClient, clinic_with_users: ClinicWithUsers):
    admin_headers = dev_headers(clinic_with_users.admin)
    viewer_headers = dev_headers(clinic_with_users.viewer)
    created = await _create_patient(api_client, admin_headers)

    list_resp = await api_client.get("/api/v1/patients", headers=viewer_headers)
    get_resp = await api_client.get(f"/api/v1/patients/{created['id']}", headers=viewer_headers)

    assert list_resp.status_code == 200
    assert get_resp.status_code == 200


async def test_audiologist_can_archive_but_not_restore(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    admin_headers = dev_headers(clinic_with_users.admin)
    audiologist_headers = dev_headers(clinic_with_users.audiologist)
    created = await _create_patient(api_client, admin_headers)

    archive_resp = await api_client.post(
        f"/api/v1/patients/{created['id']}/archive", headers=audiologist_headers
    )
    restore_resp = await api_client.post(
        f"/api/v1/patients/{created['id']}/restore", headers=audiologist_headers
    )

    assert archive_resp.status_code == 200
    assert restore_resp.status_code == 403


# --- Aislamiento entre clínicas ----------------------------------------------


async def test_patient_from_other_clinic_returns_404_not_403(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    other_clinic = await create_clinic_with_users(db_session)
    created = await _create_patient(api_client, dev_headers(clinic_with_users.admin))

    response = await api_client.get(
        f"/api/v1/patients/{created['id']}", headers=dev_headers(other_clinic.admin)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_list_does_not_leak_other_clinics_patients(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    other_clinic = await create_clinic_with_users(db_session)
    await _create_patient(api_client, dev_headers(clinic_with_users.admin), internal_code="MINE")

    response = await api_client.get(
        "/api/v1/patients?include_archived=true", headers=dev_headers(other_clinic.admin)
    )
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


# --- Auditoría ---------------------------------------------------------------


async def test_create_writes_audit_entry_in_same_operation(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    headers = dev_headers(clinic_with_users.admin)
    response = await api_client.post(
        "/api/v1/patients", json={"internal_code": "PAT-AUDIT"}, headers=headers
    )
    patient_id = uuid.UUID(response.json()["id"])
    request_id = response.headers["x-request-id"]

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.entity_id == patient_id)
    )
    entries = result.scalars().all()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "patient.created"
    assert entry.entity_type == "patient"
    assert entry.actor_user_id == clinic_with_users.admin.id
    assert entry.clinic_id == clinic_with_users.clinic.id
    assert entry.request_id == request_id


async def test_audit_update_metadata_has_only_field_names_never_values(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    headers = dev_headers(clinic_with_users.admin)
    created = await _create_patient(api_client, headers)
    secret_note = "informacion-administrativa-sensible-de-prueba"

    await api_client.patch(
        f"/api/v1/patients/{created['id']}", json={"notes": secret_note}, headers=headers
    )

    result = await db_session.execute(
        select(AuditLogORM).where(
            AuditLogORM.entity_id == uuid.UUID(created["id"]),
            AuditLogORM.action == "patient.updated",
        )
    )
    entry = result.scalar_one()

    assert entry.audit_metadata == {"changed_fields": ["notes"]}
    assert secret_note not in str(entry.audit_metadata)


# --- Transaccionalidad --------------------------------------------------------


async def test_create_rolls_back_patient_if_audit_write_fails(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    from app.patients.domain.entities import Sex
    from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
    from app.patients.service import PatientCreateData, PatientService
    from tests.factories import current_user_from

    class _BrokenAuditRepository:
        async def add(self, session, entry):  # noqa: ARG002
            raise RuntimeError("fallo simulado de auditoría")

    service = PatientService(db_session, audit_repository=_BrokenAuditRepository())
    current_user = current_user_from(clinic_with_users.admin)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        await service.create(
            current_user,
            PatientCreateData(
                internal_code="PAT-ROLLBACK",
                display_name=None,
                birth_year=None,
                sex=Sex.UNSPECIFIED,
                preferred_language="es",
                notes=None,
            ),
            "req-rollback-test",
        )

    # La sesión sigue siendo utilizable tras el rollback interno del servicio.
    found = await SqlAlchemyPatientRepository().get_by_internal_code(
        db_session, clinic_with_users.clinic.id, "PAT-ROLLBACK"
    )
    assert found is None

    audit_rows = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.action == "patient.created")
    )
    assert audit_rows.scalars().all() == []
