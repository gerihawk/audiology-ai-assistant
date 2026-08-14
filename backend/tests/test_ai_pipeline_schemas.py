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
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS


def _valid_session_notes_content() -> dict:
    return {name: {"text": "", "source_excerpt": None} for name in SESSION_NOTES_BLOCKS}


def _valid_anamnesis_content() -> dict:
    return {
        name: {"value": "", "status": "no_preguntado", "source_excerpt": None}
        for name in ANAMNESIS_FIELDS
    }


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


# --- patient_summary ------------------------------------------------------


def test_patient_summary_valido():
    content = {"text": "resumen en lenguaje llano"}
    assert validate_content_schema(AIArtifactType.PATIENT_SUMMARY, content).valid is True


def test_patient_summary_falta_campo_obligatorio():
    assert validate_content_schema(AIArtifactType.PATIENT_SUMMARY, {}).valid is False


def test_patient_summary_tipo_invalido():
    assert validate_content_schema(AIArtifactType.PATIENT_SUMMARY, {"text": 5}).valid is False


def test_patient_summary_campo_desconocido():
    content = {"text": "ok", "audience": "patient"}
    assert validate_content_schema(AIArtifactType.PATIENT_SUMMARY, content).valid is False


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


def test_anamnesis_source_excerpt_es_obligatorio_como_clave():
    """Fase 6.4.2: `source_excerpt` es obligatorio-presente-nullable
    (mismo patrón que `clinical_flags[].source_excerpt`), nunca opcional
    ni ausente — ni siquiera para `no_preguntado`."""
    content = _valid_anamnesis_content()
    del content[ANAMNESIS_FIELDS[0]]["source_excerpt"]
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


# --- las cuatro combinaciones status/source_excerpt (RFC técnico §6) -------


def test_anamnesis_informado_con_source_excerpt_no_vacio_es_valido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "Acúfenos en oído izquierdo.",
        "status": "informado",
        "source_excerpt": "acúfenos en el oído izquierdo",
    }
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is True


def test_anamnesis_informado_sin_source_excerpt_es_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "Acúfenos.",
        "status": "informado",
        "source_excerpt": None,
    }
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_anamnesis_informado_con_source_excerpt_vacio_o_solo_espacios_es_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "Acúfenos.",
        "status": "informado",
        "source_excerpt": "   ",
    }
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_anamnesis_negado_explicitamente_con_source_excerpt_no_vacio_es_valido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "El paciente niega vértigo.",
        "status": "negado_explicitamente",
        "source_excerpt": "niega vértigo",
    }
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is True


def test_anamnesis_negado_explicitamente_sin_source_excerpt_es_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "El paciente niega vértigo.",
        "status": "negado_explicitamente",
        "source_excerpt": None,
    }
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_anamnesis_no_preguntado_con_source_excerpt_null_es_valido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {"value": "", "status": "no_preguntado", "source_excerpt": None}
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is True


def test_anamnesis_no_preguntado_con_source_excerpt_inventado_es_invalido():
    """Nunca una cita inventada para un campo sin evidencia real — RFC
    técnico §6."""
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "",
        "status": "no_preguntado",
        "source_excerpt": "esto no debería estar aquí",
    }
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_anamnesis_no_determinado_con_source_excerpt_null_es_valido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "mención ambigua",
        "status": "no_determinado",
        "source_excerpt": None,
    }
    assert validate_content_schema(AIArtifactType.ANAMNESIS, content).valid is True


def test_anamnesis_no_determinado_con_source_excerpt_inventado_es_invalido():
    content = _valid_anamnesis_content()
    content[ANAMNESIS_FIELDS[0]] = {
        "value": "mención ambigua",
        "status": "no_determinado",
        "source_excerpt": "cita inventada",
    }
    result = validate_content_schema(AIArtifactType.ANAMNESIS, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


# --- session_notes -----------------------------------------------------------


def test_session_notes_valido_con_los_4_bloques():
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, _valid_session_notes_content())
    assert result.valid is True


def test_session_notes_bloque_vacio_es_valido():
    """RFC §4.7: `text=""`/`source_excerpt=None` es la única
    representación válida de "bloque no explorado"."""
    content = _valid_session_notes_content()
    content[SESSION_NOTES_BLOCKS[0]] = {"text": "", "source_excerpt": None}
    assert validate_content_schema(AIArtifactType.SESSION_NOTES, content).valid is True


def test_session_notes_texto_no_vacio_sin_excerpt_es_invalido():
    content = _valid_session_notes_content()
    content[SESSION_NOTES_BLOCKS[0]] = {
        "text": "Ajuste de volumen realizado.",
        "source_excerpt": None,
    }
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_session_notes_excerpt_sin_texto_es_invalido():
    """Nunca una cita para un bloque que declara no tener contenido."""
    content = _valid_session_notes_content()
    content[SESSION_NOTES_BLOCKS[0]] = {"text": "", "source_excerpt": "cita inventada"}
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


def test_session_notes_texto_con_excerpt_no_vacio_es_valido():
    content = _valid_session_notes_content()
    content[SESSION_NOTES_BLOCKS[0]] = {
        "text": "Ajuste de volumen realizado.",
        "source_excerpt": "ajustamos el volumen",
    }
    assert validate_content_schema(AIArtifactType.SESSION_NOTES, content).valid is True


def test_session_notes_falta_bloque_obligatorio():
    content = _valid_session_notes_content()
    del content[SESSION_NOTES_BLOCKS[0]]
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, content)
    assert result.valid is False
    assert any(SESSION_NOTES_BLOCKS[0] in e for e in result.errors)


def test_session_notes_bloque_desconocido():
    content = _valid_session_notes_content()
    content["bloque_inventado"] = {"text": "", "source_excerpt": None}
    assert validate_content_schema(AIArtifactType.SESSION_NOTES, content).valid is False


def test_session_notes_estructura_anidada_invalida():
    content = _valid_session_notes_content()
    content[SESSION_NOTES_BLOCKS[0]] = "no-es-un-objeto"
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, content)
    assert result.valid is False
    assert any(SESSION_NOTES_BLOCKS[0] in e for e in result.errors)


def test_session_notes_source_excerpt_es_obligatorio_como_clave():
    content = _valid_session_notes_content()
    del content[SESSION_NOTES_BLOCKS[0]]["source_excerpt"]
    result = validate_content_schema(AIArtifactType.SESSION_NOTES, content)
    assert result.valid is False
    assert any("source_excerpt" in e for e in result.errors)


# --- tipo no soportado ---------------------------------------------------


def test_tipo_no_registrado_lanza_error_tipado():
    # "session_notes" fue el ejemplo histórico de tipo no registrado hasta
    # la Fase 6.4.3 — ahora sí tiene esquema, así que ya no sirve como
    # caso de "no soportado" (ver test_session_notes_valido_con_los_4_bloques).
    with pytest.raises(UnsupportedArtifactTypeError):
        validate_content_schema("clinical_record", {})
