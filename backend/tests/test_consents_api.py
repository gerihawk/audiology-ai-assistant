"""Tests de integración de /api/v1/patients/{patient_id}/consents — Fase 7.1
(docs/development-plan.md). El dominio/infraestructura de `consents` ya
tenía cobertura desde el hito 6.0 (ver test_consents_repository.py); esta
suite cubre el servicio/API que faltaba: permisos, aislamiento por
clínica, paciente archivado, `consent_version` fijado por el servidor e
histórico append-only.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.consents.domain.entities import ConsentType
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.consents.service import ConsentCreateData, ConsentService
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, create_patient, current_user_from, dev_headers


async def _create_consent(
    api_client: AsyncClient,
    headers: dict[str, str],
    patient_id: str,
    **overrides,
):
    payload = {"consent_type": "procesamiento_ia", "granted": True} | overrides
    return await api_client.post(
        f"/api/v1/patients/{patient_id}/consents", json=payload, headers=headers
    )


# --- Permisos: crear (solo audiologist) --------------------------------------


async def test_audiologist_can_create_consent(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(patient.id)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["consent_type"] == "procesamiento_ia"
    assert body["granted"] is True
    assert body["patient_id"] == str(patient.id)
    assert body["granted_by"] == str(clinic_with_users.audiologist.id)
    assert body["clinical_session_id"] is None  # fuera de alcance de esta ronda


@pytest.mark.parametrize("role_attr", ["admin", "viewer"])
async def test_create_consent_forbidden_for_non_audiologist(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient, role_attr: str
):
    user = getattr(clinic_with_users, role_attr)
    response = await _create_consent(api_client, dev_headers(user), str(patient.id))
    assert response.status_code == 403


# --- Permisos: leer (admin/audiologist, nunca viewer) ------------------------


@pytest.mark.parametrize("role_attr", ["admin", "audiologist"])
async def test_read_consents_allowed_for_admin_and_audiologist(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient, role_attr: str
):
    await _create_consent(api_client, dev_headers(clinic_with_users.audiologist), str(patient.id))
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.get(
        f"/api/v1/patients/{patient.id}/consents", headers=dev_headers(user)
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1


async def test_read_consents_forbidden_for_viewer(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await api_client.get(
        f"/api/v1/patients/{patient.id}/consents", headers=dev_headers(clinic_with_users.viewer)
    )
    assert response.status_code == 403


# --- consent_version: siempre lo fija el servidor -----------------------------


async def test_ai_processing_consent_gets_configured_version(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await _create_consent(
        api_client,
        dev_headers(clinic_with_users.audiologist),
        str(patient.id),
        consent_type="procesamiento_ia",
    )
    assert response.status_code == 201
    assert response.json()["consent_version"] is not None


@pytest.mark.parametrize("consent_type", ["grabacion_audio", "almacenamiento"])
async def test_other_consent_types_have_no_version_yet(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient, consent_type: str
):
    response = await _create_consent(
        api_client,
        dev_headers(clinic_with_users.audiologist),
        str(patient.id),
        consent_type=consent_type,
    )
    assert response.status_code == 201, response.text
    assert response.json()["consent_version"] is None


async def test_client_supplied_consent_version_is_rejected(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await _create_consent(
        api_client,
        dev_headers(clinic_with_users.audiologist),
        str(patient.id),
        consent_version="9.9-fabricada-por-el-cliente",
    )
    assert response.status_code == 422


async def test_client_supplied_clinical_session_id_is_rejected(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    response = await _create_consent(
        api_client,
        dev_headers(clinic_with_users.audiologist),
        str(patient.id),
        clinical_session_id=str(uuid.uuid4()),
    )
    assert response.status_code == 422


# --- Paciente archivado / inexistente / de otra clínica ----------------------


async def test_create_consent_rejects_archived_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
):
    archived_patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id, is_archived=True
    )
    response = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(archived_patient.id)
    )
    assert response.status_code == 409


async def test_create_consent_rejects_nonexistent_patient(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_create_consent_for_other_clinic_patient_returns_404_never_403(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    db_session: AsyncSession,
):
    from tests.factories import create_clinic_with_users

    other_clinic = await create_clinic_with_users(db_session)
    other_patient = await create_patient(db_session, other_clinic.clinic.id, other_clinic.admin.id)

    response = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(other_patient.id)
    )
    assert response.status_code == 404


async def test_list_consents_for_other_clinic_patient_returns_404(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    db_session: AsyncSession,
):
    from tests.factories import create_clinic_with_users

    other_clinic = await create_clinic_with_users(db_session)
    other_patient = await create_patient(db_session, other_clinic.clinic.id, other_clinic.admin.id)

    response = await api_client.get(
        f"/api/v1/patients/{other_patient.id}/consents",
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


# --- Histórico append-only: un segundo registro no borra el anterior --------


async def test_second_consent_of_same_type_does_not_overwrite_history(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    first = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(patient.id), granted=True
    )
    assert first.status_code == 201

    second = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(patient.id), granted=False
    )
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    listed = await api_client.get(
        f"/api/v1/patients/{patient.id}/consents", headers=dev_headers(clinic_with_users.admin)
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    assert {item["id"] for item in items} == {first.json()["id"], second.json()["id"]}
    # Más reciente primero.
    assert items[0]["id"] == second.json()["id"]
    assert items[0]["granted"] is False


async def test_ai_pipeline_service_resolves_latest_after_two_registrations_via_service(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """El histórico convive con `AIPipelineService._ensure_ai_processing_consent`
    (get_latest) sin cambios en ese servicio — se ejercita aquí el camino
    completo: dos altas por `ConsentService`, `get_latest` resuelve la más
    reciente."""
    service = ConsentService(db_session)
    current_user = current_user_from(clinic_with_users.audiologist)

    await service.create(
        current_user,
        patient.id,
        ConsentCreateData(consent_type=ConsentType.PROCESAMIENTO_IA, granted=True, notes=None),
        "req-1",
    )
    second = await service.create(
        current_user,
        patient.id,
        ConsentCreateData(consent_type=ConsentType.PROCESAMIENTO_IA, granted=False, notes=None),
        "req-2",
    )

    latest = await SqlAlchemyConsentRepository().get_latest(
        db_session, clinic_with_users.clinic.id, patient.id, ConsentType.PROCESAMIENTO_IA
    )
    assert latest is not None
    assert latest.id == second.id
    assert latest.granted is False


# --- Auditoría ---------------------------------------------------------------


async def test_create_consent_writes_audit_entry(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
):
    response = await _create_consent(
        api_client, dev_headers(clinic_with_users.audiologist), str(patient.id)
    )
    assert response.status_code == 201
    consent_id = response.json()["id"]

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.entity_id == uuid.UUID(consent_id))
    )
    entry = result.scalar_one()
    assert entry.action == "consent.registered"
    assert entry.entity_type == "consent"
    assert entry.audit_metadata["consent_type"] == "procesamiento_ia"
    assert entry.audit_metadata["granted"] is True


async def test_create_rolls_back_consent_if_audit_write_fails(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    class _BrokenAuditRepository:
        async def add(self, session, entry):  # noqa: ARG002
            raise RuntimeError("fallo simulado de auditoría")

    service = ConsentService(db_session, audit_repository=_BrokenAuditRepository())
    current_user = current_user_from(clinic_with_users.audiologist)

    with pytest.raises(RuntimeError, match="fallo simulado"):
        await service.create(
            current_user,
            patient.id,
            ConsentCreateData(consent_type=ConsentType.PROCESAMIENTO_IA, granted=True, notes=None),
            "req-rollback-test",
        )

    history = await SqlAlchemyConsentRepository().list_by_patient(
        db_session, clinic_with_users.clinic.id, patient.id
    )
    assert history == []
