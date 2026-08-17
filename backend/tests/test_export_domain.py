"""Tests de dominio puro de las primitivas de exportación — Hito 6.6.1
(docs/fase-6-rfc.md §7.1/§7.3/§7.4). Sin BD, sin HTTP, sin renderizado
PDF/texto: `AIArtifact`/`AIArtifactVersion` de este módulo son instancias
construidas a mano, nunca persistidas."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
)
from app.export.domain.entities import (
    ExportableDocument,
    ExportBundle,
    ExportBundleSession,
    build_exportable_document,
    compute_content_hash,
    is_exportable,
    strip_source_excerpt,
)

_NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def _artifact(
    *,
    artifact_id: uuid.UUID | None = None,
    status: AIArtifactStatus = AIArtifactStatus.APPROVED,
    deleted_at: datetime | None = None,
    approved_by: uuid.UUID | None = None,
    approved_at: datetime | None = None,
    current_version_id: uuid.UUID | None = None,
) -> AIArtifact:
    return AIArtifact(
        id=artifact_id or uuid.uuid4(),
        clinical_session_id=uuid.uuid4(),
        artifact_type=AIArtifactType.SUMMARY,
        status=status,
        current_version_id=current_version_id or uuid.uuid4(),
        confidence=90,
        schema_version=1,
        approved_by=approved_by,
        approved_at=approved_at,
        rejected_by=None,
        rejected_at=None,
        rejection_reason=None,
        deleted_by=uuid.uuid4() if deleted_at else None,
        deleted_at=deleted_at,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _version(
    *, artifact_id: uuid.UUID, version_id: uuid.UUID | None = None, content: dict | None = None
) -> AIArtifactVersion:
    return AIArtifactVersion(
        id=version_id or uuid.uuid4(),
        ai_artifact_id=artifact_id,
        version_number=1,
        content=content if content is not None else {"text": "Resumen de prueba."},
        confidence=90,
        source_map=None,
        source=AIArtifactVersionSource.AI_GENERATED,
        generation_run_id=uuid.uuid4(),
        created_by=None,
        change_note=None,
        created_at=_NOW,
    )


# ============================================================
# A. is_exportable
# ============================================================


class TestIsExportable:
    def test_approved_and_not_deleted_is_exportable(self):
        artifact = _artifact(status=AIArtifactStatus.APPROVED)
        assert is_exportable(artifact) is True

    def test_review_pending_is_not_exportable(self):
        artifact = _artifact(status=AIArtifactStatus.REVIEW_PENDING)
        assert is_exportable(artifact) is False

    def test_rejected_is_not_exportable(self):
        artifact = _artifact(status=AIArtifactStatus.REJECTED)
        assert is_exportable(artifact) is False

    def test_approved_but_soft_deleted_is_not_exportable(self):
        artifact = _artifact(status=AIArtifactStatus.APPROVED, deleted_at=_NOW)
        assert is_exportable(artifact) is False


# ============================================================
# B. strip_source_excerpt
# ============================================================


class TestStripSourceExcerpt:
    def test_removes_source_excerpt_from_nested_anamnesis_style_content(self):
        content = {
            "tinnitus": {
                "value": "Pitido leve.",
                "status": "informado",
                "source_excerpt": "un pitido leve en el oído derecho",
            },
            "vertigo": {"value": "", "status": "no_preguntado", "source_excerpt": None},
        }
        sanitized = strip_source_excerpt(content)
        assert "source_excerpt" not in sanitized["tinnitus"]
        assert "source_excerpt" not in sanitized["vertigo"]
        assert sanitized["tinnitus"]["value"] == "Pitido leve."

    def test_removes_source_excerpt_from_list_items(self):
        content = {
            "flags": [
                {
                    "category": "vertigo",
                    "description": "Mareos frecuentes.",
                    "source_excerpt": "me mareo mucho",
                    "ruleset_name": "v1",
                }
            ]
        }
        sanitized = strip_source_excerpt(content)
        assert "source_excerpt" not in sanitized["flags"][0]
        assert sanitized["flags"][0]["description"] == "Mareos frecuentes."

    def test_content_without_source_excerpt_is_unchanged(self):
        content = {"text": "Resumen de prueba."}
        assert strip_source_excerpt(content) == content

    def test_original_content_is_never_mutated(self):
        content = {"tinnitus": {"value": "x", "status": "informado", "source_excerpt": "evidencia"}}
        snapshot = copy.deepcopy(content)
        strip_source_excerpt(content)
        assert content == snapshot

    def test_always_returns_a_copy_even_without_source_excerpt(self):
        """No solo el valor coincide (`==`) — el resultado nunca es el
        mismo objeto ni comparte sub-estructuras mutables con el
        original, con o sin `source_excerpt` presente."""
        content = {"tinnitus": {"value": "x", "status": "informado", "source_excerpt": "e"}}
        sanitized = strip_source_excerpt(content)
        assert sanitized is not content
        assert sanitized["tinnitus"] is not content["tinnitus"]

        content_without_excerpt = {"text": "Resumen de prueba."}
        sanitized_without_excerpt = strip_source_excerpt(content_without_excerpt)
        assert sanitized_without_excerpt is not content_without_excerpt

    def test_mutating_the_result_never_affects_the_original(self):
        content = {"tinnitus": {"value": "x", "status": "informado", "source_excerpt": "e"}}
        snapshot = copy.deepcopy(content)
        sanitized = strip_source_excerpt(content)
        sanitized["tinnitus"]["value"] = "mutated"
        assert content == snapshot


# ============================================================
# C. compute_content_hash
# ============================================================


class TestComputeContentHash:
    def test_same_content_produces_same_hash(self):
        content = {"text": "Resumen de prueba."}
        assert compute_content_hash(content) == compute_content_hash(copy.deepcopy(content))

    def test_key_order_does_not_affect_hash(self):
        assert compute_content_hash({"a": 1, "b": 2}) == compute_content_hash({"b": 2, "a": 1})

    def test_different_content_produces_different_hash(self):
        assert compute_content_hash({"text": "A"}) != compute_content_hash({"text": "B"})


# ============================================================
# D. build_exportable_document
# ============================================================


class TestBuildExportableDocument:
    def test_builds_document_without_source_excerpt(self):
        artifact_id = uuid.uuid4()
        version_id = uuid.uuid4()
        approved_by = uuid.uuid4()
        artifact = _artifact(
            artifact_id=artifact_id,
            current_version_id=version_id,
            approved_by=approved_by,
            approved_at=_NOW,
        )
        version = _version(
            artifact_id=artifact_id,
            version_id=version_id,
            content={
                "tinnitus": {
                    "value": "Pitido leve.",
                    "status": "informado",
                    "source_excerpt": "un pitido leve",
                }
            },
        )
        clinical_session_id = uuid.uuid4()

        document = build_exportable_document(
            clinic_name="Clínica de prueba",
            patient_internal_code="PAC-0001",
            patient_display_name="Paciente Ficticio",
            clinical_session_id=clinical_session_id,
            session_type="follow_up",
            artifact=artifact,
            version=version,
            generated_at=_NOW,
        )

        assert document.clinic_name == "Clínica de prueba"
        assert document.patient_internal_code == "PAC-0001"
        assert document.clinical_session_id == clinical_session_id
        assert document.session_type == "follow_up"
        assert document.artifact_type == AIArtifactType.SUMMARY
        assert document.version_number == 1
        assert document.approved_by == approved_by
        assert document.approved_at == _NOW
        assert "source_excerpt" not in document.content["tinnitus"]
        assert document.content_hash == compute_content_hash(document.content)
        assert document.generated_at == _NOW

    def test_session_type_none_is_accepted_and_passed_through_unconverted(self):
        """RFC §3.3: `session_type=None` es un caso legacy válido. El DTO
        de dominio lo conserva tal cual — nunca lo convierte a "Sin
        especificar" ni a ningún otro valor; esa etiqueta es
        responsabilidad exclusiva del exportador (hito 6.6.2+)."""
        artifact_id = uuid.uuid4()
        version_id = uuid.uuid4()
        artifact = _artifact(
            artifact_id=artifact_id,
            current_version_id=version_id,
            approved_by=uuid.uuid4(),
            approved_at=_NOW,
        )
        version = _version(artifact_id=artifact_id, version_id=version_id)

        document = build_exportable_document(
            clinic_name="Clínica de prueba",
            patient_internal_code="PAC-0001",
            patient_display_name=None,
            clinical_session_id=uuid.uuid4(),
            session_type=None,
            artifact=artifact,
            version=version,
            generated_at=_NOW,
        )

        assert document.session_type is None

    def test_rejects_artifact_that_is_not_exportable(self):
        artifact_id = uuid.uuid4()
        version_id = uuid.uuid4()
        artifact = _artifact(
            artifact_id=artifact_id,
            status=AIArtifactStatus.REVIEW_PENDING,
            current_version_id=version_id,
        )
        version = _version(artifact_id=artifact_id, version_id=version_id)

        with pytest.raises(AssertionError):
            build_exportable_document(
                clinic_name="Clínica de prueba",
                patient_internal_code="PAC-0001",
                patient_display_name=None,
                clinical_session_id=uuid.uuid4(),
                session_type="follow_up",
                artifact=artifact,
                version=version,
                generated_at=_NOW,
            )

    def test_rejects_version_that_is_not_the_current_one(self):
        artifact_id = uuid.uuid4()
        artifact = _artifact(
            artifact_id=artifact_id,
            current_version_id=uuid.uuid4(),
            approved_by=uuid.uuid4(),
            approved_at=_NOW,
        )
        stale_version = _version(artifact_id=artifact_id, version_id=uuid.uuid4())

        with pytest.raises(AssertionError):
            build_exportable_document(
                clinic_name="Clínica de prueba",
                patient_internal_code="PAC-0001",
                patient_display_name=None,
                clinical_session_id=uuid.uuid4(),
                session_type="follow_up",
                artifact=artifact,
                version=stale_version,
                generated_at=_NOW,
            )


# ============================================================
# E. ExportBundle / ExportBundleSession — Hito 6.7.2 (RFC §7.2, scope=patient)
# ============================================================


def _exportable_document(*, clinical_session_id: uuid.UUID) -> ExportableDocument:
    return ExportableDocument(
        clinic_name="Clínica de prueba",
        patient_internal_code="PAC-0001",
        patient_display_name="Paciente Ficticio",
        clinical_session_id=clinical_session_id,
        session_type="follow_up",
        artifact_type=AIArtifactType.SUMMARY,
        version_number=1,
        approved_by=uuid.uuid4(),
        approved_at=_NOW,
        content={"text": "Resumen de prueba."},
        content_hash="deadbeef" * 8,
        generated_at=_NOW,
    )


class TestExportBundle:
    def test_bundle_is_frozen(self):
        bundle = ExportBundle(
            clinic_name="Clínica de prueba",
            patient_internal_code="PAC-0001",
            patient_display_name=None,
            sessions=(),
        )
        with pytest.raises(AttributeError):
            bundle.clinic_name = "Otra clínica"  # type: ignore[misc]

    def test_empty_sessions_is_valid(self):
        bundle = ExportBundle(
            clinic_name="Clínica de prueba",
            patient_internal_code="PAC-0001",
            patient_display_name=None,
            sessions=(),
        )
        assert bundle.sessions == ()

    def test_session_order_is_preserved_as_given_not_resorted(self):
        """El dominio no vuelve a ordenar `sessions` — quien construye el
        bundle (`clinical_record`, hito 6.7.3+) ya decidió el orden."""
        session_id_a, session_id_b = uuid.uuid4(), uuid.uuid4()
        session_a = ExportBundleSession(
            clinical_session_id=session_id_a,
            session_type="review",
            created_at=_NOW,
            documents=(_exportable_document(clinical_session_id=session_id_a),),
        )
        session_b = ExportBundleSession(
            clinical_session_id=session_id_b,
            session_type="initial_assessment",
            created_at=_NOW,
            documents=(_exportable_document(clinical_session_id=session_id_b),),
        )
        bundle = ExportBundle(
            clinic_name="Clínica de prueba",
            patient_internal_code="PAC-0001",
            patient_display_name=None,
            sessions=(session_a, session_b),
        )
        assert [s.clinical_session_id for s in bundle.sessions] == [session_id_a, session_id_b]

    def test_session_type_none_is_preserved_as_none(self):
        session_id = uuid.uuid4()
        session = ExportBundleSession(
            clinical_session_id=session_id,
            session_type=None,
            created_at=_NOW,
            documents=(),
        )
        assert session.session_type is None
