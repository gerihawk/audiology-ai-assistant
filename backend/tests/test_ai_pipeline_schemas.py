"""Tests de los esquemas estructurales por `AIArtifactType`
(app/ai_pipeline/domain/schemas.py) — ver docs/fase-6-rfc.md §4 y §16 del
encargo de la Fase 6.1.

Un caso por artifact_type: documento válido, campo obligatorio ausente,
tipo inválido, enum inválido (solo aplica a anamnesis), campo desconocido,
estructura anidada inválida. Los casos HUMAN_EDITED válido/inválido se
cubren en test_ai_pipeline_edit_and_delete.py, donde vive la ruta
PATCH .../content real.
"""

from __future__ import annotations

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.schemas import UnsupportedArtifactTypeError, validate_content_schema
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS


def _valid_anamnesis_content() -> dict:
    return {name: {"value": "", "status": "no_preguntado"} for name in ANAMNESIS_FIELDS}


# --- transcript ---------------------------------------------------------


def test_transcript_valido():
    content = {"text": "hola", "language": "es"}
    assert validate_content_schema(AIArtifactType.TRANSCRIPT, content).valid is True


def test_transcript_con_segments_valido():
    content = {
        "text": "hola",
        "language": "es",
        "duration_ms": 1000,
        "segments": [{"speaker": "A", "start_ms": 0, "end_ms": 500, "text": "hola"}],
    }
    assert validate_content_schema(AIArtifactType.TRANSCRIPT, content).valid is True


def test_transcript_falta_campo_obligatorio():
    result = validate_content_schema(AIArtifactType.TRANSCRIPT, {"text": "hola"})
    assert result.valid is False
    assert any("language" in e for e in result.errors)


def test_transcript_tipo_invalido():
    result = validate_content_schema(AIArtifactType.TRANSCRIPT, {"text": 123, "language": "es"})
    assert result.valid is False


def test_transcript_campo_desconocido():
    result = validate_content_schema(
        AIArtifactType.TRANSCRIPT, {"text": "hola", "language": "es", "extra": "no"}
    )
    assert result.valid is False


def test_transcript_segmento_anidado_invalido():
    content = {
        "text": "hola",
        "language": "es",
        "segments": [{"speaker": "A", "start_ms": "no-es-int", "end_ms": 500, "text": "hola"}],
    }
    result = validate_content_schema(AIArtifactType.TRANSCRIPT, content)
    assert result.valid is False
    assert any("segments[0]" in e for e in result.errors)


# --- summary -------------------------------------------------------------


def test_summary_valido():
    assert validate_content_schema(AIArtifactType.SUMMARY, {"text": "resumen"}).valid is True


def test_summary_falta_campo_obligatorio():
    assert validate_content_schema(AIArtifactType.SUMMARY, {}).valid is False


def test_summary_tipo_invalido():
    assert validate_content_schema(AIArtifactType.SUMMARY, {"text": 5}).valid is False


def test_summary_campo_desconocido():
    result = validate_content_schema(AIArtifactType.SUMMARY, {"text": "ok", "patient_text": "no"})
    assert result.valid is False


# --- clinical_flags --------------------------------------------------------


def test_clinical_flags_valido():
    content = {
        "flags": [
            {
                "category": "otalgia",
                "description": "Dolor de oído referido.",
                "source_excerpt": "me duele el oído",
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    assert validate_content_schema(AIArtifactType.CLINICAL_FLAGS, content).valid is True


def test_clinical_flags_source_excerpt_null_es_valido():
    content = {
        "flags": [
            {
                "category": "otalgia",
                "description": "d",
                "source_excerpt": None,
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    assert validate_content_schema(AIArtifactType.CLINICAL_FLAGS, content).valid is True


def test_clinical_flags_falta_campo_obligatorio():
    result = validate_content_schema(AIArtifactType.CLINICAL_FLAGS, {})
    assert result.valid is False


def test_clinical_flags_estructura_anidada_invalida():
    content = {"flags": [{"category": "otalgia"}]}
    result = validate_content_schema(AIArtifactType.CLINICAL_FLAGS, content)
    assert result.valid is False
    assert any("flags[0]" in e for e in result.errors)


def test_clinical_flags_campo_desconocido_en_item():
    content = {
        "flags": [
            {
                "category": "otalgia",
                "description": "d",
                "source_excerpt": None,
                "ruleset_name": "r",
                "confidence": 90,
            }
        ]
    }
    assert validate_content_schema(AIArtifactType.CLINICAL_FLAGS, content).valid is False


# --- missing_information ----------------------------------------------------


def test_missing_information_valido():
    content = {"items": [{"topic": "tinnitus", "suggested_question": "¿Desde cuándo?"}]}
    assert validate_content_schema(AIArtifactType.MISSING_INFORMATION, content).valid is True


def test_missing_information_falta_campo_obligatorio():
    assert validate_content_schema(AIArtifactType.MISSING_INFORMATION, {}).valid is False


def test_missing_information_tipo_invalido():
    content = {"items": "no-es-una-lista"}
    assert validate_content_schema(AIArtifactType.MISSING_INFORMATION, content).valid is False


def test_missing_information_estructura_anidada_invalida():
    content = {"items": [{"topic": "tinnitus"}]}
    result = validate_content_schema(AIArtifactType.MISSING_INFORMATION, content)
    assert result.valid is False
    assert any("items[0]" in e for e in result.errors)


# --- anamnesis ---------------------------------------------------------------


def test_anamnesis_valido_con_los_20_campos():
    result = validate_content_schema(AIArtifactType.ANAMNESIS, _valid_anamnesis_content())
    assert result.valid is True


def test_anamnesis_falta_campo_obligatorio():
    content = _valid_anamnesis_content()
    del content[ANAMNESIS_FIELDS[0]]
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any(ANAMNESIS_FIELDS[0] in e for e in result.errors)


def test_anamnesis_campo_desconocido():
    content = _valid_anamnesis_content()
    content["campo_inventado"] = {"value": "", "status": "no_preguntado"}
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is False


def test_anamnesis_tipo_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {"value": 123, "status": "no_preguntado"}
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is False


def test_anamnesis_enum_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {"value": "", "status": "estado_inventado"}
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("status" in e for e in result.errors)


def test_anamnesis_estructura_anidada_invalida():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = "no-es-un-objeto"
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any(ANAMNESIS_FIELDS[0] in e for e in result.errors)


def test_anamnesis_no_exige_source_excerpt_todavia():
    """Hito 6.1: la estructura cerrada de HOY no incluye `source_excerpt`
    — eso llega con el grounding real de anamnesis en el hito 6.4."""
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {"value": "acúfenos", "status": "informado"}
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is True


# --- tipo no soportado ---------------------------------------------------


def test_tipo_no_registrado_lanza_error_tipado():
    with pytest.raises(UnsupportedArtifactTypeError):
        validate_content_schema("session_notes", {})
