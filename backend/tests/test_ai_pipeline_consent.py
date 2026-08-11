"""Consentimiento bloqueante en AIPipelineService.run_pipeline — hito 6.0
de la Fase 6 (docs/fase-6-rfc.md §9.1, docs/ai-pipeline-architecture.md
§7.3). Con `AI_PROCESSING_CONSENT_ENFORCED` desactivado (valor por
defecto) el comportamiento es idéntico al del resto de la suite — este
archivo solo cubre el flag activado."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline import service as ai_pipeline_service_module
from app.consents.domain.entities import Consent, ConsentType
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.core.config import get_settings
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, dev_headers


def _enforce_consent(monkeypatch, *, version: str = "1.0") -> None:
    settings = get_settings().model_copy(
        update={"ai_processing_consent_enforced": True, "ai_processing_consent_version": version}
    )
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)


async def _grant_consent(
    db_session: AsyncSession,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    granted_by: uuid.UUID,
    granted: bool = True,
    version: str = "1.0",
) -> None:
    await SqlAlchemyConsentRepository().add(
        db_session,
        Consent(
            id=uuid.uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_id,
            clinical_session_id=None,
            consent_type=ConsentType.PROCESAMIENTO_IA,
            granted=granted,
            consent_version=version,
            granted_by=granted_by,
            recorded_at=None,
            notes=None,
        ),
    )
    await db_session.commit()


async def test_run_pipeline_blocks_when_enforced_and_no_consent(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    monkeypatch,
):
    _enforce_consent(monkeypatch)
    headers = dev_headers(clinic_with_users.admin)
    session_response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.audiologist.id),
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["id"]

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline", headers=headers
    )

    assert response.status_code == 409
    assert "consentimiento" in response.json()["error"]["message"].lower()


async def test_run_pipeline_succeeds_when_enforced_and_consent_granted(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    _enforce_consent(monkeypatch)
    await _grant_consent(
        db_session,
        clinic_id=clinic_with_users.clinic.id,
        patient_id=patient.id,
        granted_by=clinic_with_users.admin.id,
    )
    headers = dev_headers(clinic_with_users.admin)
    session_response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.audiologist.id),
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    session_id = session_response.json()["id"]

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline", headers=headers
    )

    assert response.status_code == 201, response.text


async def test_run_pipeline_blocks_when_consent_version_is_stale(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    _enforce_consent(monkeypatch, version="2.0")
    await _grant_consent(
        db_session,
        clinic_id=clinic_with_users.clinic.id,
        patient_id=patient.id,
        granted_by=clinic_with_users.admin.id,
        version="1.0",  # versión antigua, no la vigente ("2.0")
    )
    headers = dev_headers(clinic_with_users.admin)
    session_response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.audiologist.id),
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    session_id = session_response.json()["id"]

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline", headers=headers
    )

    assert response.status_code == 409
