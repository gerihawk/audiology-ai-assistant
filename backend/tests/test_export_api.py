"""Tests de integración de la exportación individual de documentos
clínicos — Hito 6.6.4 (docs/fase-6-rfc.md §7.2/§7.5, scope=session).

Reutiliza los fixtures/factories ya existentes de la Fase 6
(`clinic_with_users`, `patient`, `_create_session`/
`_run_pipeline_and_get_first_artifact`, mismo patrón que
`test_ai_pipeline_edit_and_delete.py`) — sin duplicar infraestructura de
test."""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import uuid

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.export.domain.entities import ExportableDocument
from app.export.service import ExportService
from app.patients.domain.entities import Patient
from app.users.domain.entities import Role
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_patient,
    create_user,
    current_user_from,
    dev_headers,
)


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


async def _approved_artifact(
    api_client: AsyncClient, headers: dict[str, str], session_id: str
) -> dict:
    artifact = await _run_pipeline_and_get_first_artifact(api_client, headers, session_id)
    response = await api_client.post(
        f"/api/v1/ai-artifacts/{artifact['id']}/approve", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _export_url(artifact_id: str, export_format: str) -> str:
    return f"/api/v1/ai-artifacts/{artifact_id}/export?format={export_format}"


_FILENAME_RE = re.compile(r'attachment; filename="([^"]+)"')


def _filename_from_response(response) -> str:
    match = _FILENAME_RE.match(response.headers["content-disposition"])
    assert match is not None, response.headers["content-disposition"]
    return match.group(1)


# ============================================================
# A/B/C/D — export exitoso, Content-Type, Content-Disposition
# ============================================================


class TestSuccessfulExport:
    async def test_export_pdf_of_approved_artifact_returns_200(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)

        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    async def test_export_text_of_approved_artifact_returns_200(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        response = await api_client.get(_export_url(artifact["id"], "text"), headers=headers)

        assert response.status_code == 200
        assert "=== DOCUMENTO CLÍNICO EXPORTADO ===" in response.text

    async def test_pdf_content_type(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.headers["content-type"] == "application/pdf"

    async def test_text_content_type(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(_export_url(artifact["id"], "text"), headers=headers)
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    async def test_content_disposition_is_attachment_with_filename(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)

        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment; filename=")
        assert _filename_from_response(response).endswith(".pdf")

    async def test_unknown_format_returns_422(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(
            f"/api/v1/ai-artifacts/{artifact['id']}/export?format=docx", headers=headers
        )
        assert response.status_code == 422


# ============================================================
# E — filename ASCII-safe, sin path traversal ni header injection
# ============================================================


class TestFilenameSafety:
    async def test_filename_is_ascii_safe_and_has_no_path_or_control_characters(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        db_session: AsyncSession,
    ):
        # `internal_code` con caracteres deliberadamente peligrosos si se
        # volcaran sin sanear en `Content-Disposition` (encargo 6.6.4:
        # "impedir CR/LF/header injection; no usar rutas; no permitir
        # ../"). El código interno normalmente no admitiría esto en
        # `PatientService`, pero el filename debe ser seguro con
        # independencia de esa validación de entrada.
        dangerous_patient = await create_patient(
            db_session,
            clinic_with_users.clinic.id,
            clinic_with_users.admin.id,
            internal_code="../../etc/passwd\r\nX-Injected: 1",
        )
        session = await _create_session(
            api_client,
            dev_headers(clinic_with_users.admin),
            str(dangerous_patient.id),
            str(clinic_with_users.audiologist.id),
        )
        artifact = await _approved_artifact(
            api_client, dev_headers(clinic_with_users.admin), session["id"]
        )

        response = await api_client.get(
            _export_url(artifact["id"], "pdf"), headers=dev_headers(clinic_with_users.admin)
        )

        assert response.status_code == 200
        filename = _filename_from_response(response)
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", filename), filename
        assert ".." not in filename
        assert "/" not in filename
        assert "\r" not in filename and "\n" not in filename


# ============================================================
# F — Unicode español presente
# ============================================================


class TestSpanishUnicode:
    async def test_pdf_preserves_spanish_accented_characters(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)

        reader = PdfReader(io.BytesIO(response.content))
        text = "\n".join(page.extract_text() for page in reader.pages)
        assert "acúfenos" in text or "í" in text

    async def test_text_preserves_spanish_accented_characters(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        response = await api_client.get(_export_url(artifact["id"], "text"), headers=headers)
        assert "acúfenos" in response.text


# ============================================================
# G/H/I/J — errores de autorización/tenant
# ============================================================


class TestAuthorizationAndTenantIsolation:
    async def test_nonexistent_artifact_returns_404(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers
    ):
        response = await api_client.get(
            _export_url(str(uuid.uuid4()), "pdf"), headers=dev_headers(clinic_with_users.admin)
        )
        assert response.status_code == 404

    async def test_cross_clinic_artifact_returns_404(
        self, api_client: AsyncClient, db_session: AsyncSession
    ):
        clinic_a = await create_clinic_with_users(db_session)
        clinic_b = await create_clinic_with_users(db_session)
        patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)
        session = await _create_session(
            api_client,
            dev_headers(clinic_a.admin),
            str(patient_a.id),
            str(clinic_a.audiologist.id),
        )
        artifact = await _approved_artifact(api_client, dev_headers(clinic_a.admin), session["id"])

        response = await api_client.get(
            _export_url(artifact["id"], "pdf"), headers=dev_headers(clinic_b.admin)
        )
        assert response.status_code == 404

    async def test_viewer_cannot_export(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        artifact = await _approved_artifact(
            api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
        )
        response = await api_client.get(
            _export_url(artifact["id"], "pdf"), headers=dev_headers(clinic_with_users.viewer)
        )
        assert response.status_code == 403

    async def test_non_owner_audiologist_in_same_clinic_can_export(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        clinical_session: dict,
        db_session: AsyncSession,
    ):
        """RFC §7.5: exportar no aplica la restricción de propiedad de
        `AIArtifactAction.EDIT/APPROVE` — cualquier audiologist de la
        clínica puede exportar, no solo el profesional responsable de la
        sesión (encargo 6.6.4, caso J)."""
        other_audiologist = await create_user(
            db_session, clinic_with_users.clinic.id, role=Role.AUDIOLOGIST
        )
        # `clinical_session` fue creada con `clinic_with_users.audiologist`
        # como profesional responsable — `other_audiologist` no lo es.
        artifact = await _approved_artifact(
            api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
        )

        response = await api_client.get(
            _export_url(artifact["id"], "pdf"), headers=dev_headers(other_audiologist)
        )
        assert response.status_code == 200


# ============================================================
# K/L/M/N — elegibilidad
# ============================================================


class TestEligibility:
    async def test_deleted_artifact_returns_404(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])
        delete_response = await api_client.delete(
            f"/api/v1/ai-artifacts/{artifact['id']}", headers=headers
        )
        assert delete_response.status_code == 204

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 404

    async def test_review_pending_artifact_returns_409(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _run_pipeline_and_get_first_artifact(
            api_client, headers, clinical_session["id"]
        )
        assert artifact["status"] == "review_pending"

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 409

    async def test_rejected_artifact_returns_409(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _run_pipeline_and_get_first_artifact(
            api_client, headers, clinical_session["id"]
        )
        reject_response = await api_client.post(
            f"/api/v1/ai-artifacts/{artifact['id']}/reject", headers=headers
        )
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 409

    async def test_editing_approved_artifact_reopens_review_and_export_returns_409(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        """El estado manda sobre el historial: existe una versión
        aprobada anterior (v1), pero `current_version_id` apunta ahora a
        una v2 `review_pending` — exportar debe fallar igualmente
        (encargo 6.6.4, caso N)."""
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        edit_response = await api_client.patch(
            f"/api/v1/ai-artifacts/{artifact['id']}/content",
            json={
                "content": {"text": "editado tras aprobar", "language": "es"},
                "change_note": None,
            },
            headers=headers,
        )
        assert edit_response.status_code == 200
        assert edit_response.json()["status"] == "review_pending"
        assert edit_response.json()["version_number"] == 2

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 409


# ============================================================
# O/P — auditoría
# ============================================================


class TestAudit:
    async def test_export_writes_document_exported_with_exact_metadata(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        clinical_session: dict,
        db_session: AsyncSession,
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 200

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "document.exported",
                AuditLogORM.entity_id == uuid.UUID(artifact["id"]),
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_user_id == clinic_with_users.admin.id
        assert entry.entity_type == "ai_artifact"

        metadata = entry.audit_metadata
        assert metadata == {
            "clinical_session_id": clinical_session["id"],
            "artifact_id": artifact["id"],
            "artifact_type": artifact["artifact_type"],
            "version_number": artifact["version_number"],
            "format": "pdf",
        }

        forbidden_keys = {
            "content",
            "source_excerpt",
            "source_map",
            "patient_name",
            "transcript",
            "bytes",
            "provider",
            "model",
            "estimated_cost_usd",
        }
        assert forbidden_keys.isdisjoint(metadata.keys())
        serialized = json.dumps(metadata)
        assert "acúfenos" not in serialized  # nada del transcript/content clínico
        assert "Paciente de test" not in serialized  # nunca patient_display_name

    async def test_exporter_failure_writes_no_audit_entry(
        self,
        api_client: AsyncClient,
        clinic_with_users: ClinicWithUsers,
        clinical_session: dict,
        db_session: AsyncSession,
    ):
        """Requiere sustituir el exporter por uno que falle — no
        alcanzable vía HTTP puro, así que se invoca `ExportService`
        directamente sobre la misma `db_session` de test (mismo patrón
        transaccional que la ruta HTTP: si el renderizado falla, ninguna
        auditoría debe persistirse)."""
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        class _FailingExporter:
            def export(self, document: ExportableDocument) -> bytes:
                raise RuntimeError("fallo simulado de renderizado")

        service = ExportService(db_session, pdf_exporter=_FailingExporter())

        with pytest.raises(RuntimeError):
            await service.export(
                current_user_from(clinic_with_users.admin),
                uuid.UUID(artifact["id"]),
                "pdf",
                "test-request-id",
            )

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "document.exported",
                AuditLogORM.entity_id == uuid.UUID(artifact["id"]),
            )
        )
        assert result.scalars().all() == []


# ============================================================
# Q — cero ficheros temporales/residuos
# ============================================================


class TestNoTemporaryFiles:
    async def test_export_creates_no_files_on_disk(
        self, api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
    ):
        headers = dev_headers(clinic_with_users.admin)
        artifact = await _approved_artifact(api_client, headers, clinical_session["id"])

        tmp_dir = tempfile.gettempdir()
        before = set(os.listdir(tmp_dir))

        response = await api_client.get(_export_url(artifact["id"], "pdf"), headers=headers)
        assert response.status_code == 200

        after = set(os.listdir(tmp_dir))
        assert after - before == set()
