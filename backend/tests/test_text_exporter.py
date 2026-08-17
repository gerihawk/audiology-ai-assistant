"""Tests de `TextDocumentExporter` — Hito 6.6.2 (docs/fase-6-rfc.md
§7.1/§7.4). Sin BD, sin HTTP: opera exclusivamente sobre `ExportableDocument`
ya construidos a mano (equivalente a lo que produciría `build_exportable_document`
de 6.6.1, sin repetir aquí su propio andamiaje de `AIArtifact`/`AIArtifactVersion`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.ai_pipeline.domain.entities import AIArtifactType
from app.export.domain.entities import ExportableDocument, ExportBundle, ExportBundleSession
from app.export.infrastructure.text_exporter import TextDocumentExporter
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS

_APPROVED_AT = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
_GENERATED_AT = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def _document(
    *,
    artifact_type: AIArtifactType,
    content: dict,
    session_type: str | None = "follow_up",
    patient_display_name: str | None = "Paciente Ficticio",
) -> ExportableDocument:
    return ExportableDocument(
        clinic_name="Clínica de prueba",
        patient_internal_code="PAC-0001",
        patient_display_name=patient_display_name,
        clinical_session_id=uuid.uuid4(),
        session_type=session_type,
        artifact_type=artifact_type,
        version_number=3,
        approved_by=uuid.uuid4(),
        approved_at=_APPROVED_AT,
        content=content,
        content_hash="deadbeef" * 8,
        generated_at=_GENERATED_AT,
    )


_exporter = TextDocumentExporter()


# ============================================================
# A. Contrato general — bytes, determinismo, cabecera
# ============================================================


class TestGeneralContract:
    def test_output_is_bytes_not_str(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        result = _exporter.export(document)
        assert isinstance(result, bytes)

    def test_output_decodes_as_utf8(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Pitido leve, oído derecho."}
        )
        result = _exporter.export(document)
        assert "oído" in result.decode("utf-8")

    def test_rendering_is_deterministic(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        assert _exporter.export(document) == _exporter.export(document)

    def test_header_contains_required_metadata(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        text = _exporter.export(document).decode("utf-8")

        assert "Clínica de prueba" in text
        assert "PAC-0001" in text
        assert "Paciente Ficticio" in text
        assert str(document.clinical_session_id) in text
        assert "follow_up" in text
        assert "summary" in text
        assert "Versión: 3" in text
        assert str(document.approved_by) in text
        assert _APPROVED_AT.isoformat() in text
        assert _GENERATED_AT.isoformat() in text
        assert document.content_hash in text

    def test_session_type_none_renders_as_sin_especificar(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."}, session_type=None
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Sin especificar" in text

    def test_patient_without_display_name_omits_parentheses(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY,
            content={"text": "Resumen."},
            patient_display_name=None,
        )
        text = _exporter.export(document).decode("utf-8")
        assert "PAC-0001" in text
        assert "(" not in text.split("Paciente:")[1].split("\n")[0]

    def test_output_never_contains_internal_metadata_terms(self):
        """`ExportableDocument` no transporta `confidence`/`source_map`/
        provider/model/generation_run/coste (hito 6.6.1) — esta prueba es
        una red de seguridad frente a una regresión futura que los
        reintroduzca en el renderizado."""
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        text = _exporter.export(document).decode("utf-8").lower()
        for forbidden in (
            "source_excerpt",
            "source_map",
            "confidence",
            "provider",
            "generation_run",
            "estimated_cost",
        ):
            assert forbidden not in text

    def test_output_never_contains_raw_json_braces(self):
        document = _document(
            artifact_type=AIArtifactType.ANAMNESIS,
            content={name: {"value": "x", "status": "informado"} for name in ANAMNESIS_FIELDS[:2]}
            | {name: {"value": "", "status": "no_preguntado"} for name in ANAMNESIS_FIELDS[2:]},
        )
        text = _exporter.export(document).decode("utf-8")
        assert "{" not in text
        assert "}" not in text


# ============================================================
# B. SUMMARY / PATIENT_SUMMARY
# ============================================================


class TestProseArtifacts:
    def test_summary_renders_text_verbatim(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Consulta de seguimiento."}
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Consulta de seguimiento." in text

    def test_patient_summary_renders_text_verbatim(self):
        document = _document(
            artifact_type=AIArtifactType.PATIENT_SUMMARY,
            content={"text": "Explicación en lenguaje llano."},
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Explicación en lenguaje llano." in text


# ============================================================
# C. TRANSCRIPT
# ============================================================


class TestTranscript:
    def test_renders_language_and_text(self):
        document = _document(
            artifact_type=AIArtifactType.TRANSCRIPT,
            content={"text": "Hola, ¿qué tal?", "language": "es"},
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Idioma: es" in text
        assert "Hola, ¿qué tal?" in text
        assert "Duración" not in text
        assert "Segmentos" not in text

    def test_renders_optional_duration_and_segments_when_present(self):
        document = _document(
            artifact_type=AIArtifactType.TRANSCRIPT,
            content={
                "text": "Hola.",
                "language": "es",
                "duration_ms": 4200,
                "segments": [
                    {"speaker": "PACIENTE", "start_ms": 0, "end_ms": 1000, "text": "Hola."}
                ],
            },
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Duración: 4200 ms" in text
        assert "Segmentos:" in text
        assert "[0-1000] PACIENTE: Hola." in text


# ============================================================
# D. CLINICAL_FLAGS
# ============================================================


class TestClinicalFlags:
    def test_includes_mandatory_ruleset_disclaimer(self):
        """docs/clinical-safety.md §7: obligatorio en todo lugar donde se
        exporten `clinical_flags`, con independencia de que estén vacías
        o no — hito 6.6.5, hueco detectado en la verificación de cierre."""
        document = _document(artifact_type=AIArtifactType.CLINICAL_FLAGS, content={"flags": []})
        text = _exporter.export(document).decode("utf-8")
        assert "Checklist de demostración" in text
        assert "No validado clínicamente" in text

    def test_renders_each_flag_without_source_excerpt(self):
        document = _document(
            artifact_type=AIArtifactType.CLINICAL_FLAGS,
            content={
                "flags": [
                    {
                        "category": "vertigo",
                        "description": "Mareos frecuentes.",
                        "ruleset_name": "v1",
                    }
                ]
            },
        )
        text = _exporter.export(document).decode("utf-8")
        assert "[vertigo] Mareos frecuentes. (v1)" in text

    def test_empty_flags_renders_placeholder(self):
        document = _document(artifact_type=AIArtifactType.CLINICAL_FLAGS, content={"flags": []})
        text = _exporter.export(document).decode("utf-8")
        assert "(sin información)" in text


# ============================================================
# E. MISSING_INFORMATION
# ============================================================


class TestMissingInformation:
    def test_renders_each_item(self):
        document = _document(
            artifact_type=AIArtifactType.MISSING_INFORMATION,
            content={
                "items": [
                    {
                        "topic": "Antecedentes familiares",
                        "suggested_question": "¿Algún caso en la familia?",
                    }
                ]
            },
        )
        text = _exporter.export(document).decode("utf-8")
        assert "Tema: Antecedentes familiares" in text
        assert "Pregunta sugerida: ¿Algún caso en la familia?" in text

    def test_empty_items_renders_placeholder(self):
        document = _document(
            artifact_type=AIArtifactType.MISSING_INFORMATION, content={"items": []}
        )
        text = _exporter.export(document).decode("utf-8")
        assert "(sin información)" in text


# ============================================================
# F. ANAMNESIS — orden determinista, nunca dict.items()
# ============================================================


class TestAnamnesis:
    def _content_with(self, field_name: str, *, value: str, status: str) -> dict:
        content = {name: {"value": "", "status": "no_preguntado"} for name in ANAMNESIS_FIELDS}
        content[field_name] = {"value": value, "status": status}
        return content

    def test_renders_field_value_and_status(self):
        content = self._content_with("tinnitus", value="Pitido leve.", status="informado")
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _exporter.export(document).decode("utf-8")
        assert "Tinnitus [informado]:" in text
        assert "Pitido leve." in text

    def test_empty_value_renders_placeholder(self):
        content = self._content_with("tinnitus", value="", status="no_preguntado")
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _exporter.export(document).decode("utf-8")
        assert "Tinnitus [no_preguntado]:" in text

    def test_order_follows_anamnesis_fields_constant_not_dict_insertion_order(self):
        """El `content` se construye insertando las claves en orden
        INVERSO al canónico — si el renderizador dependiera de
        `dict.items()`, el orden de salida sería el inverso."""
        reversed_fields = list(reversed(ANAMNESIS_FIELDS))
        content = {name: {"value": name, "status": "informado"} for name in reversed_fields}
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _exporter.export(document).decode("utf-8")

        positions = [text.index(f"[informado]:\n{name}") for name in ANAMNESIS_FIELDS]
        assert positions == sorted(positions)

    def test_fields_absent_from_content_are_skipped_without_crashing(self):
        content = self._content_with("tinnitus", value="Pitido leve.", status="informado")
        del content["vertigo_o_inestabilidad"]
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _exporter.export(document).decode("utf-8")
        assert "Vertigo o inestabilidad" not in text


# ============================================================
# G. SESSION_NOTES — orden determinista, nunca dict.items()
# ============================================================


class TestSessionNotes:
    def test_renders_block_text(self):
        content = {name: {"text": ""} for name in SESSION_NOTES_BLOCKS}
        content["next_steps"] = {"text": "Revisión en 4 semanas."}
        document = _document(artifact_type=AIArtifactType.SESSION_NOTES, content=content)
        text = _exporter.export(document).decode("utf-8")
        assert "Next steps:" in text
        assert "Revisión en 4 semanas." in text

    def test_unexplored_block_renders_placeholder(self):
        content = {name: {"text": ""} for name in SESSION_NOTES_BLOCKS}
        document = _document(artifact_type=AIArtifactType.SESSION_NOTES, content=content)
        text = _exporter.export(document).decode("utf-8")
        assert "(no explorado)" in text

    def test_order_follows_session_notes_blocks_constant_not_dict_insertion_order(self):
        reversed_blocks = list(reversed(SESSION_NOTES_BLOCKS))
        content = {name: {"text": name} for name in reversed_blocks}
        document = _document(artifact_type=AIArtifactType.SESSION_NOTES, content=content)
        text = _exporter.export(document).decode("utf-8")

        positions = [text.index(f":\n{name}") for name in SESSION_NOTES_BLOCKS]
        assert positions == sorted(positions)


# ============================================================
# H. export_many — Hito 6.7.2 (RFC §7.2, scope=patient)
# ============================================================


def _session(
    *,
    clinical_session_id: uuid.UUID | None = None,
    session_type: str | None = "follow_up",
    created_at: datetime = _APPROVED_AT,
    documents: tuple[ExportableDocument, ...] = (),
) -> ExportBundleSession:
    return ExportBundleSession(
        clinical_session_id=clinical_session_id or uuid.uuid4(),
        session_type=session_type,
        created_at=created_at,
        documents=documents,
    )


def _bundle(
    *,
    sessions: tuple[ExportBundleSession, ...] = (),
    patient_display_name: str | None = "Paciente Ficticio",
) -> ExportBundle:
    return ExportBundle(
        clinic_name="Clínica de prueba",
        patient_internal_code="PAC-0001",
        patient_display_name=patient_display_name,
        sessions=sessions,
    )


class TestExportMany:
    def test_empty_bundle_returns_header_only_without_crashing(self):
        result = _exporter.export_many(_bundle(sessions=()))
        text = result.decode("utf-8")
        assert isinstance(result, bytes)
        assert "Clínica de prueba" in text
        assert "PAC-0001" in text
        assert "SESIÓN" not in text

    def test_one_session_one_document(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        bundle = _bundle(sessions=(_session(documents=(document,)),))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "Resumen." in text
        assert "=== SESIÓN 1 ===" in text

    def test_one_session_multiple_artifact_types(self):
        summary = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        transcript = _document(
            artifact_type=AIArtifactType.TRANSCRIPT, content={"text": "Hola.", "language": "es"}
        )
        bundle = _bundle(sessions=(_session(documents=(summary, transcript)),))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "Resumen." in text
        assert "Idioma: es" in text
        assert text.index("Resumen.") < text.index("Idioma: es")

    def test_multiple_sessions_preserve_bundle_order(self):
        """El exportador no reordena — usa exactamente el orden en el
        que llegan las sesiones en el bundle."""
        doc_a = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Sesión B."})
        doc_b = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Sesión A."})
        session_review = _session(session_type="review", documents=(doc_a,))
        session_initial = _session(session_type="initial_assessment", documents=(doc_b,))
        bundle = _bundle(sessions=(session_review, session_initial))
        text = _exporter.export_many(bundle).decode("utf-8")

        assert text.index("=== SESIÓN 1 ===") < text.index("=== SESIÓN 2 ===")
        assert text.index("Sesión B.") < text.index("Sesión A.")

    def test_sessions_are_deterministically_separated(self):
        session_1 = _session(documents=())
        session_2 = _session(documents=())
        bundle = _bundle(sessions=(session_1, session_2))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "=== SESIÓN 1 ===" in text
        assert "=== SESIÓN 2 ===" in text
        assert text.index("=== SESIÓN 1 ===") < text.index("=== SESIÓN 2 ===")

    def test_session_type_none_renders_as_sin_especificar(self):
        bundle = _bundle(sessions=(_session(session_type=None, documents=()),))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "Sin especificar" in text

    def test_unicode_survives(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Pitido leve, oído derecho."}
        )
        bundle = _bundle(sessions=(_session(documents=(document,)),))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "oído" in text

    def test_clinical_flags_disclaimer_still_present(self):
        document = _document(artifact_type=AIArtifactType.CLINICAL_FLAGS, content={"flags": []})
        bundle = _bundle(sessions=(_session(documents=(document,)),))
        text = _exporter.export_many(bundle).decode("utf-8")
        assert "Checklist de demostración" in text
        assert "No validado clínicamente" in text

    def test_output_never_contains_internal_metadata_terms(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        bundle = _bundle(sessions=(_session(documents=(document,)),))
        text = _exporter.export_many(bundle).decode("utf-8").lower()
        for forbidden in (
            "source_excerpt",
            "source_map",
            "confidence",
            "provider",
            "generation_run",
            "estimated_cost",
        ):
            assert forbidden not in text

    def test_rendering_is_deterministic(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        bundle = _bundle(sessions=(_session(documents=(document,)),))
        assert _exporter.export_many(bundle) == _exporter.export_many(bundle)

    def test_existing_export_of_single_document_is_unchanged(self):
        """Regresión crítica: `export_many` no debe alterar `export`."""
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        assert _exporter.export(document) == _exporter.export(document)
        text = _exporter.export(document).decode("utf-8")
        assert "=== DOCUMENTO CLÍNICO EXPORTADO ===" in text
        assert "HISTORIA CLÍNICA LONGITUDINAL" not in text
