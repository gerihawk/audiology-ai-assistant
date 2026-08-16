"""Tests de `PdfDocumentExporter` — Hito 6.6.3 (docs/fase-6-rfc.md
§7.1/§7.4). Sin BD, sin HTTP: opera exclusivamente sobre `ExportableDocument`
ya construidos a mano, igual que `test_text_exporter.py` (6.6.2). Usa
`pypdf` (solo dev, nunca producción) para verificar que el PDF generado es
válido y que su texto extraído contiene lo esperado."""

from __future__ import annotations

import io
import os
import tempfile
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from app.ai_pipeline.domain.entities import AIArtifactType
from app.export.domain.entities import ExportableDocument
from app.export.infrastructure.pdf_exporter import PdfDocumentExporter
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


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


_exporter = PdfDocumentExporter()


# ============================================================
# A. Contrato general — PDF válido, cabecera, ausencia de metadata interna
# ============================================================


class TestGeneralContract:
    def test_output_starts_with_pdf_magic_bytes(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        result = _exporter.export(document)
        assert result[:5] == b"%PDF-"

    def test_output_parses_as_valid_pdf(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        result = _exporter.export(document)
        reader = PdfReader(io.BytesIO(result))
        assert len(reader.pages) >= 1

    def test_header_contains_required_metadata(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        text = _extract_text(_exporter.export(document))

        assert "Clínica de prueba" in text
        assert "PAC-0001" in text
        assert "Paciente Ficticio" in text
        assert str(document.clinical_session_id) in text
        assert "follow_up" in text
        assert "summary" in text
        assert "3" in text  # versión
        assert str(document.approved_by) in text
        assert document.content_hash in text.replace("\n", "")

    def test_session_type_none_renders_as_sin_especificar(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."}, session_type=None
        )
        text = _extract_text(_exporter.export(document))
        assert "Sin especificar" in text

    def test_output_never_contains_internal_metadata_terms(self):
        """`ExportableDocument` no transporta `confidence`/`source_map`/
        provider/model/generation_run/coste (hito 6.6.1) — red de
        seguridad frente a una regresión que los reintroduzca."""
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        text = _extract_text(_exporter.export(document)).lower()
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
        text = _extract_text(_exporter.export(document))
        assert "{" not in text
        assert "}" not in text

    def test_unsupported_artifact_type_raises(self):
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        document = replace(document, artifact_type="not_a_real_type")
        with pytest.raises(ValueError):
            _exporter.export(document)


# ============================================================
# B. Unicode español
# ============================================================


class TestSpanishUnicode:
    def test_all_target_characters_survive_export_and_extraction(self):
        sample = "ñ á é í ó ú ü ¿Cómo estás? ¡Hola! niño güisqui año"
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": sample})
        text = _extract_text(_exporter.export(document))
        for char in "ñáéíóúü¿¡":
            assert char in text

    def test_xml_special_characters_do_not_break_rendering(self):
        """`Paragraph` interpreta un subconjunto de XML — un valor clínico
        con `<`/`>`/`&` literales debe escaparse, nunca romper el PDF ni
        desaparecer silenciosamente."""
        sample = 'Valor < 5 & > 2, referencia "comillas".'
        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": sample})
        pdf_bytes = _exporter.export(document)
        assert pdf_bytes[:5] == b"%PDF-"
        text = _extract_text(pdf_bytes)
        assert "5" in text and "2" in text


# ============================================================
# C. Los 7 artifact_type renderizan sin error
# ============================================================


class TestAllArtifactTypesRender:
    def test_transcript(self):
        document = _document(
            artifact_type=AIArtifactType.TRANSCRIPT,
            content={
                "text": "Hola, ¿qué tal?",
                "language": "es",
                "duration_ms": 4200,
                "segments": [
                    {"speaker": "PACIENTE", "start_ms": 0, "end_ms": 1000, "text": "Hola."}
                ],
            },
        )
        text = _extract_text(_exporter.export(document))
        assert "Idioma" in text and "es" in text
        assert "Segmentos" in text
        assert "PACIENTE" in text

    def test_summary(self):
        document = _document(
            artifact_type=AIArtifactType.SUMMARY, content={"text": "Consulta de seguimiento."}
        )
        text = _extract_text(_exporter.export(document))
        assert "Consulta de seguimiento." in text

    def test_patient_summary(self):
        document = _document(
            artifact_type=AIArtifactType.PATIENT_SUMMARY,
            content={"text": "Explicación en lenguaje llano."},
        )
        text = _extract_text(_exporter.export(document))
        assert "Explicación en lenguaje llano." in text

    def test_clinical_flags(self):
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
        text = _extract_text(_exporter.export(document))
        assert "vertigo" in text
        assert "Mareos frecuentes." in text
        # docs/clinical-safety.md §7: obligatorio en todo lugar donde se
        # exporten clinical_flags — hito 6.6.5, hueco detectado en la
        # verificación de cierre.
        assert "Checklist de demostración" in text
        assert "No validado clínicamente" in text

    def test_missing_information(self):
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
        text = _extract_text(_exporter.export(document))
        assert "Antecedentes familiares" in text
        assert "¿Algún caso en la familia?" in text

    def test_anamnesis(self):
        content = {name: {"value": "", "status": "no_preguntado"} for name in ANAMNESIS_FIELDS}
        content["tinnitus"] = {"value": "Pitido leve.", "status": "informado"}
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _extract_text(_exporter.export(document))
        assert "Tinnitus" in text
        assert "informado" in text
        assert "Pitido leve." in text

    def test_session_notes(self):
        content = {name: {"text": ""} for name in SESSION_NOTES_BLOCKS}
        content["next_steps"] = {"text": "Revisión en 4 semanas."}
        document = _document(artifact_type=AIArtifactType.SESSION_NOTES, content=content)
        text = _extract_text(_exporter.export(document))
        assert "Next steps" in text
        assert "Revisión en 4 semanas." in text


# ============================================================
# D. Orden determinista — ANAMNESIS / SESSION_NOTES
# ============================================================


class TestDeterministicOrder:
    def test_anamnesis_order_follows_canonical_constant_not_dict_insertion_order(self):
        reversed_fields = list(reversed(ANAMNESIS_FIELDS))
        content = {name: {"value": name, "status": "informado"} for name in reversed_fields}
        document = _document(artifact_type=AIArtifactType.ANAMNESIS, content=content)
        text = _extract_text(_exporter.export(document))

        positions = [text.index(name) for name in ANAMNESIS_FIELDS]
        assert positions == sorted(positions)

    def test_session_notes_order_follows_canonical_constant_not_dict_insertion_order(self):
        reversed_blocks = list(reversed(SESSION_NOTES_BLOCKS))
        content = {name: {"text": name} for name in reversed_blocks}
        document = _document(artifact_type=AIArtifactType.SESSION_NOTES, content=content)
        text = _extract_text(_exporter.export(document))

        positions = [text.index(name) for name in SESSION_NOTES_BLOCKS]
        assert positions == sorted(positions)

    def test_clinical_flags_preserve_list_order(self):
        content = {
            "flags": [
                {"category": "c1", "description": "primero", "ruleset_name": "r1"},
                {"category": "c2", "description": "segundo", "ruleset_name": "r2"},
                {"category": "c3", "description": "tercero", "ruleset_name": "r3"},
            ]
        }
        document = _document(artifact_type=AIArtifactType.CLINICAL_FLAGS, content=content)
        text = _extract_text(_exporter.export(document))
        positions = [text.index(word) for word in ("primero", "segundo", "tercero")]
        assert positions == sorted(positions)


# ============================================================
# E. Multipágina
# ============================================================


class TestMultiPage:
    def test_long_document_produces_more_than_one_page(self):
        long_items = [
            {"topic": f"Tema número {i}", "suggested_question": f"¿Pregunta número {i}?"}
            for i in range(200)
        ]
        document = _document(
            artifact_type=AIArtifactType.MISSING_INFORMATION, content={"items": long_items}
        )
        pdf_bytes = _exporter.export(document)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) > 1


# ============================================================
# F. Cero ficheros temporales/residuos
# ============================================================


class TestNoTemporaryFiles:
    def test_export_creates_no_files_on_disk(self):
        tmp_dir = tempfile.gettempdir()
        before = set(os.listdir(tmp_dir))

        document = _document(artifact_type=AIArtifactType.SUMMARY, content={"text": "Resumen."})
        _exporter.export(document)

        after = set(os.listdir(tmp_dir))
        assert after - before == set()
