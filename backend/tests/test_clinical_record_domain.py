"""Tests de dominio puro de la historia clínica longitudinal — Hito
6.7.1 (docs/fase-6-rfc.md §3.4/§8). Sin BD, sin HTTP: `AIArtifact`/
`AIArtifactVersion` de este módulo son instancias construidas a mano,
nunca persistidas."""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
)
from app.clinical_record.domain.entities import (
    ClinicalRecordPatientRef,
    LoadedSessionArtifacts,
    build_clinical_record_page,
    build_session_entries,
    find_current_anamnesis_baseline,
    is_eligible_artifact,
    sort_documents_by_pipeline_order,
    strip_source_excerpt,
)

_NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def _artifact(
    *,
    artifact_type: AIArtifactType = AIArtifactType.SUMMARY,
    status: AIArtifactStatus = AIArtifactStatus.APPROVED,
    deleted_at: datetime | None = None,
    approved_by: uuid.UUID | None = None,
    approved_at: datetime | None = None,
    current_version_id: uuid.UUID | None = None,
) -> AIArtifact:
    return AIArtifact(
        id=uuid.uuid4(),
        clinical_session_id=uuid.uuid4(),
        artifact_type=artifact_type,
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
        source_map={"text": "map interno, nunca debe salir del DTO"},
        source=AIArtifactVersionSource.AI_GENERATED,
        generation_run_id=uuid.uuid4(),
        created_by=None,
        change_note=None,
        created_at=_NOW,
    )


def _approved_pair(
    *,
    artifact_type: AIArtifactType,
    approved_at: datetime,
    content: dict | None = None,
) -> tuple[AIArtifact, AIArtifactVersion]:
    version_id = uuid.uuid4()
    artifact = _artifact(
        artifact_type=artifact_type,
        approved_by=uuid.uuid4(),
        approved_at=approved_at,
        current_version_id=version_id,
    )
    version = _version(artifact_id=artifact.id, version_id=version_id, content=content)
    return artifact, version


# ============================================================
# A. is_eligible_artifact
# ============================================================


class TestIsEligibleArtifact:
    def test_approved_and_not_deleted_is_eligible(self):
        artifact = _artifact(status=AIArtifactStatus.APPROVED)
        assert is_eligible_artifact(artifact) is True

    def test_review_pending_is_not_eligible(self):
        artifact = _artifact(status=AIArtifactStatus.REVIEW_PENDING)
        assert is_eligible_artifact(artifact) is False

    def test_rejected_is_not_eligible(self):
        artifact = _artifact(status=AIArtifactStatus.REJECTED)
        assert is_eligible_artifact(artifact) is False

    def test_approved_but_soft_deleted_is_not_eligible(self):
        artifact = _artifact(status=AIArtifactStatus.APPROVED, deleted_at=_NOW)
        assert is_eligible_artifact(artifact) is False


# ============================================================
# B. strip_source_excerpt
# ============================================================


class TestStripSourceExcerpt:
    def test_removes_source_excerpt_from_nested_content(self):
        content = {
            "tinnitus": {
                "value": "Pitido leve.",
                "status": "informado",
                "source_excerpt": "un pitido leve en el oído derecho",
            }
        }
        sanitized = strip_source_excerpt(content)
        assert "source_excerpt" not in sanitized["tinnitus"]
        assert sanitized["tinnitus"]["value"] == "Pitido leve."

    def test_removes_source_excerpt_from_list_items(self):
        content = {
            "flags": [
                {
                    "category": "vertigo",
                    "description": "Mareos frecuentes.",
                    "source_excerpt": "me mareo mucho",
                }
            ]
        }
        sanitized = strip_source_excerpt(content)
        assert "source_excerpt" not in sanitized["flags"][0]

    def test_original_content_is_never_mutated(self):
        content = {"tinnitus": {"value": "x", "source_excerpt": "evidencia"}}
        snapshot = copy.deepcopy(content)
        strip_source_excerpt(content)
        assert content == snapshot


# ============================================================
# C. sort_documents_by_pipeline_order
# ============================================================


class TestSortDocumentsByPipelineOrder:
    def test_orders_documents_by_pipeline_step_order(self):
        artifact_a, version_a = _approved_pair(
            artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW
        )
        artifact_b, version_b = _approved_pair(
            artifact_type=AIArtifactType.TRANSCRIPT, approved_at=_NOW
        )
        artifact_c, version_c = _approved_pair(
            artifact_type=AIArtifactType.SUMMARY, approved_at=_NOW
        )
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=(
                (artifact_a, version_a),
                (artifact_b, version_b),
                (artifact_c, version_c),
            ),
        )
        (entry,) = build_session_entries([session])
        assert [doc.artifact_type for doc in entry.documents] == [
            AIArtifactType.TRANSCRIPT,
            AIArtifactType.SUMMARY,
            AIArtifactType.ANAMNESIS,
        ]

    def test_empty_sequence_returns_empty_tuple(self):
        assert sort_documents_by_pipeline_order([]) == ()


# ============================================================
# D. find_current_anamnesis_baseline
# ============================================================


class TestFindCurrentAnamnesisBaseline:
    def test_empty_list_returns_none(self):
        assert find_current_anamnesis_baseline([]) is None

    def test_picks_most_recently_approved(self):
        older, _ = _approved_pair(
            artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW - timedelta(days=10)
        )
        newer, _ = _approved_pair(artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW)
        assert find_current_anamnesis_baseline([older, newer]).id == newer.id

    def test_exact_tie_in_approved_at_is_resolved_deterministically(self):
        a, _ = _approved_pair(artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW)
        b, _ = _approved_pair(artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW)
        expected = max(a, b, key=lambda artifact: artifact.id)

        result_ab = find_current_anamnesis_baseline([a, b])
        result_ba = find_current_anamnesis_baseline([b, a])

        assert result_ab.id == expected.id
        assert result_ba.id == expected.id


# ============================================================
# E. build_session_entries / build_clinical_record_page
# ============================================================


class TestBuildSessionEntries:
    def test_no_sessions_returns_empty_tuple(self):
        assert build_session_entries([]) == ()

    def test_session_with_no_documents_yields_empty_documents(self):
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=(),
        )
        (entry,) = build_session_entries([session])
        assert entry.documents == ()

    def test_filters_out_review_pending_rejected_and_deleted(self):
        approved, approved_version = _approved_pair(
            artifact_type=AIArtifactType.SUMMARY, approved_at=_NOW
        )
        pending = _artifact(
            artifact_type=AIArtifactType.CLINICAL_FLAGS, status=AIArtifactStatus.REVIEW_PENDING
        )
        pending_version = _version(artifact_id=pending.id, version_id=pending.current_version_id)
        rejected = _artifact(
            artifact_type=AIArtifactType.MISSING_INFORMATION, status=AIArtifactStatus.REJECTED
        )
        rejected_version = _version(artifact_id=rejected.id, version_id=rejected.current_version_id)
        deleted, deleted_version = _approved_pair(
            artifact_type=AIArtifactType.PATIENT_SUMMARY, approved_at=_NOW
        )
        deleted.deleted_at = _NOW
        deleted.deleted_by = uuid.uuid4()

        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=(
                (approved, approved_version),
                (pending, pending_version),
                (rejected, rejected_version),
                (deleted, deleted_version),
            ),
        )
        (entry,) = build_session_entries([session])
        assert [doc.artifact_type for doc in entry.documents] == [AIArtifactType.SUMMARY]

    def test_multiple_sessions_are_ordered_chronologically(self):
        session_a = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="initial_assessment",
            created_at=_NOW,
            artifacts=(),
        )
        session_b = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW - timedelta(days=5),
            artifacts=(),
        )
        session_c = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="review",
            created_at=_NOW + timedelta(days=5),
            artifacts=(),
        )
        entries = build_session_entries([session_a, session_b, session_c])
        assert [entry.session_type for entry in entries] == [
            "follow_up",
            "initial_assessment",
            "review",
        ]

    def test_two_historical_anamnesis_both_remain_only_latest_is_baseline(self):
        older, older_version = _approved_pair(
            artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW - timedelta(days=30)
        )
        newer, newer_version = _approved_pair(
            artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW
        )
        session_old = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="initial_assessment",
            created_at=_NOW - timedelta(days=30),
            artifacts=((older, older_version),),
        )
        session_new = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="review",
            created_at=_NOW,
            artifacts=((newer, newer_version),),
        )
        entries = build_session_entries([session_old, session_new])

        old_doc = entries[0].documents[0]
        new_doc = entries[1].documents[0]
        assert old_doc.ai_artifact_id == older.id
        assert new_doc.ai_artifact_id == newer.id
        assert old_doc.is_current_baseline is False
        assert new_doc.is_current_baseline is True

    def test_session_notes_never_receives_baseline_semantics(self):
        anamnesis, anamnesis_version = _approved_pair(
            artifact_type=AIArtifactType.ANAMNESIS, approved_at=_NOW - timedelta(days=1)
        )
        session_notes, session_notes_version = _approved_pair(
            artifact_type=AIArtifactType.SESSION_NOTES, approved_at=_NOW
        )
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=(
                (anamnesis, anamnesis_version),
                (session_notes, session_notes_version),
            ),
        )
        (entry,) = build_session_entries([session])
        by_type = {doc.artifact_type: doc for doc in entry.documents}
        assert by_type[AIArtifactType.SESSION_NOTES].is_current_baseline is False
        assert by_type[AIArtifactType.ANAMNESIS].is_current_baseline is True

    def test_session_type_none_is_preserved_as_none(self):
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type=None,
            created_at=_NOW,
            artifacts=(),
        )
        (entry,) = build_session_entries([session])
        assert entry.session_type is None

    def test_document_never_exposes_source_map_or_internal_metadata(self):
        artifact, version = _approved_pair(
            artifact_type=AIArtifactType.SUMMARY,
            approved_at=_NOW,
            content={"text": "x", "source_excerpt": "evidencia"},
        )
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=((artifact, version),),
        )
        (entry,) = build_session_entries([session])
        document_fields = asdict(entry.documents[0])
        assert "source_map" not in document_fields
        assert "confidence" not in document_fields
        assert "source_excerpt" not in document_fields["content"]

    def test_builders_do_not_mutate_input_objects_or_content(self):
        artifact, version = _approved_pair(
            artifact_type=AIArtifactType.SUMMARY,
            approved_at=_NOW,
            content={"text": "x", "source_excerpt": "evidencia"},
        )
        artifact_snapshot = copy.deepcopy(artifact)
        version_content_snapshot = copy.deepcopy(version.content)
        session = LoadedSessionArtifacts(
            clinical_session_id=uuid.uuid4(),
            session_type="follow_up",
            created_at=_NOW,
            artifacts=((artifact, version),),
        )

        build_session_entries([session])

        assert artifact == artifact_snapshot
        assert version.content == version_content_snapshot


class TestBuildClinicalRecordPage:
    def test_zero_sessions_zero_documents(self):
        patient = ClinicalRecordPatientRef(
            patient_id=uuid.uuid4(), internal_code="PAC-0001", display_name="Paciente Ficticio"
        )
        page = build_clinical_record_page(patient=patient, sessions=[], total=0, limit=20, offset=0)
        assert page.sessions == ()
        assert page.total == 0
        assert page.patient == patient

    def test_pagination_metadata_is_passed_through(self):
        patient = ClinicalRecordPatientRef(
            patient_id=uuid.uuid4(), internal_code="PAC-0002", display_name=None
        )
        page = build_clinical_record_page(
            patient=patient, sessions=[], total=42, limit=10, offset=20
        )
        assert (page.total, page.limit, page.offset) == (42, 10, 20)
