"""Tests HTTP/end-to-end de la historia clínica longitudinal — Hito 6.7.4
(docs/fase-6-rfc.md §7.2/§7.5, scope=patient).

Reutiliza los fixtures/factories ya existentes de la Fase 6
(`clinic_with_users`, `patient`, `create_clinical_session`, mismo patrón
que `test_export_api.py`/`test_clinical_record_service.py`) sin duplicar
infraestructura de test. No repite la cobertura de `test_clinical_record_
service.py` (paginación fina, aislamiento de clínica sobre `get_record`,
render byte a byte de `export_many()` en 6.7.2) ni la de
`test_export_api.py` (export individual scope=session, sin tocar aquí).
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
)
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.audit_log.infrastructure.orm import AuditLogORM
from app.clinical_record.service import ClinicalRecordService
from app.clinical_sessions.domain.entities import ClinicalSession
from app.core.messages.es import RULESET_DISCLAIMER
from app.export.domain.entities import ExportBundle
from app.patients.domain.entities import Patient
from app.users.domain.entities import Role
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_clinical_session,
    create_patient,
    create_user,
    current_user_from,
    dev_headers,
)

_ARTIFACT_REPO = SqlAlchemyAIArtifactRepository()

_DEFAULT_CONTENT_BY_TYPE: dict[AIArtifactType, dict] = {
    AIArtifactType.TRANSCRIPT: {"language": "es", "text": "transcripción de prueba"},
    AIArtifactType.SUMMARY: {"text": "resumen de prueba"},
    AIArtifactType.PATIENT_SUMMARY: {"text": "resumen paciente de prueba"},
    AIArtifactType.CLINICAL_FLAGS: {"flags": []},
    AIArtifactType.MISSING_INFORMATION: {"items": []},
    AIArtifactType.ANAMNESIS: {},
    AIArtifactType.SESSION_NOTES: {},
}


async def _create_approved_artifact(
    session: AsyncSession,
    clinical_session: ClinicalSession,
    *,
    artifact_type: AIArtifactType,
    approved_by: uuid.UUID,
    approved_at: datetime | None = None,
    content: dict | None = None,
) -> AIArtifact:
    """Crea directamente un `AIArtifact` `APPROVED` con su versión vigente
    — mismo patrón que `test_clinical_record_service.py::_create_artifact`,
    sin pasar por `AIPipelineService`/mock pipeline (que no garantiza los
    7 `AIArtifactType` ni control fino de `approved_at`)."""
    artifact_id = uuid.uuid4()
    now = approved_at or datetime.now(UTC)
    await _ARTIFACT_REPO.insert_new(
        session,
        AIArtifact(
            id=artifact_id,
            clinical_session_id=clinical_session.id,
            artifact_type=artifact_type,
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
    version = await _ARTIFACT_REPO.insert_version(
        session,
        AIArtifactVersion(
            id=uuid.uuid4(),
            ai_artifact_id=artifact_id,
            version_number=1,
            content=content if content is not None else _DEFAULT_CONTENT_BY_TYPE[artifact_type],
            confidence=80,
            source_map={"text": "map interno, nunca debe salir del DTO"},
            source=AIArtifactVersionSource.AI_GENERATED,
            generation_run_id=None,
            created_by=None,
            change_note=None,
            created_at=now,
        ),
    )
    updated = await _ARTIFACT_REPO.update_disposition(
        session,
        clinical_session.clinic_id,
        artifact_id,
        {
            "current_version_id": version.id,
            "status": AIArtifactStatus.APPROVED.value,
            "approved_by": approved_by,
            "approved_at": now,
            "updated_at": now,
        },
    )
    await session.commit()
    assert updated is not None
    return updated


def _view_url(patient_id: str, *, limit: int | None = None, offset: int | None = None) -> str:
    params = []
    if limit is not None:
        params.append(f"limit={limit}")
    if offset is not None:
        params.append(f"offset={offset}")
    query = f"?{'&'.join(params)}" if params else ""
    return f"/api/v1/patients/{patient_id}/clinical-record{query}"


def _export_url(
    patient_id: str, export_format: str, *, limit: int | None = None, offset: int | None = None
) -> str:
    params = [f"format={export_format}"]
    if limit is not None:
        params.append(f"limit={limit}")
    if offset is not None:
        params.append(f"offset={offset}")
    return f"/api/v1/patients/{patient_id}/clinical-record/export?{'&'.join(params)}"


_FILENAME_RE = re.compile(r'attachment; filename="([^"]+)"')


def _filename_from_response(response) -> str:
    match = _FILENAME_RE.match(response.headers["content-disposition"])
    assert match is not None, response.headers["content-disposition"]
    return match.group(1)


# ============================================================
# Vista JSON longitudinal
# ============================================================


class TestClinicalRecordView:
    async def test_view_returns_200_with_expected_structure(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        response = await api_client.get(
            _view_url(str(patient.id)), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["patient_id"] == str(patient.id)
        assert body["patient_internal_code"] == patient.internal_code
        assert body["sessions"] == []
        assert body["total"] == 0
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert "ai_disclaimer" in body

    async def test_viewer_can_view(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _view_url(str(patient.id)), headers=dev_headers(clinic_with_users.viewer)
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_cross_clinic_patient_returns_404(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, db_session: AsyncSession
    ):
        other_clinic = await create_clinic_with_users(db_session)
        other_patient = await create_patient(
            db_session, other_clinic.clinic.id, other_clinic.admin.id
        )
        response = await api_client.get(
            _view_url(str(other_patient.id)), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 404

    async def test_pagination_reflects_total_limit_offset(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        for _ in range(3):
            await create_clinical_session(
                db_session,
                clinic_with_users.clinic.id,
                patient.id,
                clinic_with_users.audiologist.id,
                clinic_with_users.admin.id,
            )

        response = await api_client.get(
            _view_url(str(patient.id), limit=2, offset=1),
            headers=dev_headers(clinic_with_users.admin),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["limit"] == 2
        assert body["offset"] == 1
        assert len(body["sessions"]) == 2

    async def test_json_never_exposes_internal_generation_metadata(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            content={
                "motivo_consulta": {
                    "value": "acúfenos",
                    "status": "informado",
                    "source_excerpt": "cita textual que nunca debe salir del DTO",
                }
            },
        )

        response = await api_client.get(
            _view_url(str(patient.id)), headers=dev_headers(clinic_with_users.admin)
        )
        serialized = response.text
        assert "source_excerpt" not in serialized
        assert "source_map" not in serialized
        assert "confidence" not in serialized
        assert "provider" not in serialized
        assert "estimated_cost" not in serialized
        assert "cita textual que nunca debe salir del DTO" not in serialized

    async def test_clinical_flags_include_ruleset_disclaimer_other_types_do_not(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.CLINICAL_FLAGS,
            approved_by=clinic_with_users.audiologist.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _view_url(str(patient.id)), headers=dev_headers(clinic_with_users.admin)
        )
        documents = response.json()["sessions"][0]["documents"]
        by_type = {doc["artifact_type"]: doc for doc in documents}
        assert by_type["clinical_flags"]["ruleset_disclaimer"] == RULESET_DISCLAIMER
        assert by_type["summary"]["ruleset_disclaimer"] is None


# ============================================================
# Exportación longitudinal scope=patient
# ============================================================


class TestClinicalRecordExport:
    async def test_export_pdf_returns_200_with_longitudinal_content(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
            content={"text": "resumen con acúfenos"},
        )

        response = await api_client.get(
            _export_url(str(patient.id), "pdf"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"
        reader = PdfReader(io.BytesIO(response.content))
        text = "\n".join(page.extract_text() for page in reader.pages)
        assert "HISTORIA CLÍNICA LONGITUDINAL" in text or "acúfenos" in text

    async def test_export_text_returns_200_with_longitudinal_content(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
            content={"text": "resumen con acúfenos"},
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "=== HISTORIA CLÍNICA LONGITUDINAL ===" in response.text
        assert "acúfenos" in response.text

    async def test_viewer_cannot_export(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _export_url(str(patient.id), "pdf"), headers=dev_headers(clinic_with_users.viewer)
        )
        assert response.status_code == 403

    async def test_audiologist_can_export(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"),
            headers=dev_headers(clinic_with_users.audiologist),
        )
        assert response.status_code == 200

    async def test_non_owner_audiologist_can_export(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        """Sin ownership por profesional (encargo 6.7.4): cualquier
        audiologist de la clínica puede exportar, no solo el responsable
        de la sesión."""
        other_audiologist = await create_user(
            db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST
        )
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"), headers=dev_headers(other_audiologist)
        )
        assert response.status_code == 200

    async def test_filename_is_ascii_safe(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        db_session: AsyncSession,
    ):
        dangerous_patient = await create_patient(
            db_session,
            clinic_with_users.clinic.id,
            clinic_with_users.admin.id,
            internal_code="../../etc/passwd\r\nX-Injected: 1",
        )
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            dangerous_patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _export_url(str(dangerous_patient.id), "pdf"),
            headers=dev_headers(clinic_with_users.admin),
        )
        assert response.status_code == 200
        filename = _filename_from_response(response)
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", filename), filename
        assert ".." not in filename
        assert "/" not in filename
        assert "\r" not in filename and "\n" not in filename

    async def test_no_approved_documents_view_200_export_409(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        view_response = await api_client.get(
            _view_url(str(patient.id)), headers=dev_headers(clinic_with_users.admin)
        )
        assert view_response.status_code == 200

        export_response = await api_client.get(
            _export_url(str(patient.id), "pdf"), headers=dev_headers(clinic_with_users.admin)
        )
        assert export_response.status_code == 409

    async def test_multiple_sessions_and_documents_export_in_order(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        first_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        second_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        # Insertados deliberadamente en orden NO canónico dentro de cada
        # sesión (mismo criterio que test_clinical_record_service.py).
        await _create_approved_artifact(
            db_session,
            first_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
            content={"text": "resumen sesión uno"},
        )
        await _create_approved_artifact(
            db_session,
            first_session,
            artifact_type=AIArtifactType.TRANSCRIPT,
            approved_by=clinic_with_users.audiologist.id,
            content={"language": "es", "text": "transcripción sesión uno"},
        )
        await _create_approved_artifact(
            db_session,
            second_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
            content={"text": "resumen sesión dos"},
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200
        text = response.text
        first_pos = text.index("resumen sesión uno")
        transcript_pos = text.index("transcripción sesión uno")
        second_pos = text.index("resumen sesión dos")
        # Orden de sesiones: cronológico. Orden de documentos dentro de la
        # primera sesión: PIPELINE_STEP_ORDER (TRANSCRIPT antes que SUMMARY).
        assert transcript_pos < first_pos < second_pos

    async def test_two_historical_anamnesis_both_exported_in_their_own_session(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        older_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        newer_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            older_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 1, 1, tzinfo=UTC),
            content={"motivo_consulta": {"value": "anamnesis antigua", "status": "informado"}},
        )
        await _create_approved_artifact(
            db_session,
            newer_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 6, 1, tzinfo=UTC),
            content={"motivo_consulta": {"value": "anamnesis reciente", "status": "informado"}},
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"), headers=dev_headers(clinic_with_users.admin)
        )
        text = response.text
        assert "anamnesis antigua" in text
        assert "anamnesis reciente" in text
        first_session_block = text.split("=== SESIÓN 2 ===")[0]
        assert "anamnesis antigua" in first_session_block
        assert "anamnesis reciente" not in first_session_block

    async def test_invalid_format_returns_422(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        response = await api_client.get(
            f"/api/v1/patients/{patient.id}/clinical-record/export?format=docx",
            headers=dev_headers(clinic_with_users.admin),
        )
        assert response.status_code == 422


# ============================================================
# Auditoría
# ============================================================


class TestClinicalRecordExportAudit:
    async def test_export_does_not_write_clinical_record_viewed(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        response = await api_client.get(
            _export_url(str(patient.id), "pdf"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "clinical_record.viewed",
                AuditLogORM.entity_id == patient.id,
            )
        )
        assert result.scalars().all() == []

    async def test_export_writes_exactly_one_document_exported_with_exact_metadata(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
            content={"text": "resumen con acúfenos"},
        )

        response = await api_client.get(
            _export_url(str(patient.id), "text"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "document.exported",
                AuditLogORM.entity_id == patient.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_user_id == clinic_with_users.admin.id
        assert entry.entity_type == "patient"

        metadata = entry.audit_metadata
        assert metadata == {
            "scope": "patient",
            "patient_id": str(patient.id),
            "format": "text",
            "limit": None,
            "offset": 0,
            "sessions_included": 1,
        }

        forbidden_keys = {
            "content",
            "source_excerpt",
            "source_map",
            "patient_name",
            "patient_display_name",
            "transcript",
            "bytes",
            "provider",
            "model",
            "estimated_cost_usd",
            "artifact_id",
            "session_ids",
        }
        assert forbidden_keys.isdisjoint(metadata.keys())
        serialized = json.dumps(metadata)
        assert "acúfenos" not in serialized
        assert "Paciente de test" not in serialized

    async def test_exporter_failure_writes_no_audit_entry(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        class _FailingExporter:
            def export(self, document):  # pragma: no cover - no ejercitado aquí
                raise RuntimeError("fallo simulado de renderizado")

            def export_many(self, bundle: ExportBundle) -> bytes:
                raise RuntimeError("fallo simulado de renderizado")

        service = ClinicalRecordService(db_session, pdf_exporter=_FailingExporter())

        with pytest.raises(RuntimeError):
            await service.export_record(
                current_user_from(clinic_with_users.admin),
                patient.id,
                export_format="pdf",
                limit=None,
                offset=0,
                request_id="test-request-id",
            )

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "document.exported",
                AuditLogORM.entity_id == patient.id,
            )
        )
        assert result.scalars().all() == []

    async def test_export_creates_no_temporary_files(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
    ):
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        tmp_dir = tempfile.gettempdir()
        before = set(os.listdir(tmp_dir))

        response = await api_client.get(
            _export_url(str(patient.id), "pdf"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 200

        after = set(os.listdir(tmp_dir))
        assert after - before == set()


# ============================================================
# Guardarraíl de sesiones máximas exportables (clinical_record_export_max_sessions)
# ============================================================


def _patch_max_sessions(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    from app.core.config import get_settings as real_get_settings

    patched_settings = real_get_settings().model_copy(
        update={"clinical_record_export_max_sessions": value}
    )
    monkeypatch.setattr("app.clinical_record.service.get_settings", lambda: patched_settings)


class TestClinicalRecordExportSessionLimit:
    async def test_total_sessions_exceeds_max_without_limit_returns_conflict(
        self,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_max_sessions(monkeypatch, 2)
        for _ in range(3):
            clinical_session = await create_clinical_session(
                db_session,
                clinic_with_users.clinic.id,
                patient.id,
                clinic_with_users.audiologist.id,
                clinic_with_users.admin.id,
            )
            await _create_approved_artifact(
                db_session,
                clinical_session,
                artifact_type=AIArtifactType.SUMMARY,
                approved_by=clinic_with_users.audiologist.id,
            )

        from app.core.exceptions import ConflictError

        service = ClinicalRecordService(db_session)
        with pytest.raises(ConflictError):
            await service.export_record(
                current_user_from(clinic_with_users.admin),
                patient.id,
                export_format="text",
                limit=None,
                offset=0,
                request_id="req-limit-1",
            )

    async def test_limit_greater_than_max_is_rejected(
        self,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_max_sessions(monkeypatch, 2)
        clinical_session = await create_clinical_session(
            db_session,
            clinic_with_users.clinic.id,
            patient.id,
            clinic_with_users.audiologist.id,
            clinic_with_users.admin.id,
        )
        await _create_approved_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        from app.core.exceptions import ConflictError

        service = ClinicalRecordService(db_session)
        with pytest.raises(ConflictError):
            await service.export_record(
                current_user_from(clinic_with_users.admin),
                patient.id,
                export_format="text",
                limit=5,
                offset=0,
                request_id="req-limit-2",
            )

    async def test_explicit_limit_within_max_segments_successfully(
        self,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_max_sessions(monkeypatch, 2)
        sessions = []
        for i in range(3):
            clinical_session = await create_clinical_session(
                db_session,
                clinic_with_users.clinic.id,
                patient.id,
                clinic_with_users.audiologist.id,
                clinic_with_users.admin.id,
            )
            await _create_approved_artifact(
                db_session,
                clinical_session,
                artifact_type=AIArtifactType.SUMMARY,
                approved_by=clinic_with_users.audiologist.id,
                content={"text": f"resumen {i}"},
            )
            sessions.append(clinical_session)

        service = ClinicalRecordService(db_session)
        result = await service.export_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            export_format="text",
            limit=2,
            offset=0,
            request_id="req-limit-3",
        )
        text = result.content.decode("utf-8")
        assert "resumen 0" in text
        assert "resumen 1" in text
        assert "resumen 2" not in text

    async def test_offset_exports_later_window(
        self,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _patch_max_sessions(monkeypatch, 2)
        for i in range(3):
            clinical_session = await create_clinical_session(
                db_session,
                clinic_with_users.clinic.id,
                patient.id,
                clinic_with_users.audiologist.id,
                clinic_with_users.admin.id,
            )
            await _create_approved_artifact(
                db_session,
                clinical_session,
                artifact_type=AIArtifactType.SUMMARY,
                approved_by=clinic_with_users.audiologist.id,
                content={"text": f"resumen {i}"},
            )

        service = ClinicalRecordService(db_session)
        result = await service.export_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            export_format="text",
            limit=2,
            offset=2,
            request_id="req-limit-4",
        )
        text = result.content.decode("utf-8")
        assert "resumen 2" in text
        assert "resumen 0" not in text
        assert "resumen 1" not in text
