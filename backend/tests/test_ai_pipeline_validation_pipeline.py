"""Tests de `validate_generated_content`
(app/ai_pipeline/domain/validation_pipeline.py) — orden de validación,
grounding aplicado por artefacto y política de rechazo. Ver
docs/fase-6-rfc.md §5.1/§5.3/§5.4 y §15 del encargo de la Fase 6.1 (los
casos ligados al estado de un campo de anamnesis viven aquí, no en
test_ai_pipeline_grounding_validator.py)."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.validation_pipeline import validate_generated_content
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS

_TRANSCRIPT = "El paciente refiere acúfenos en el oído izquierdo. Niega vértigo."


def _anamnesis_content(**overrides: dict) -> dict:
    content = {name: {"value": "", "status": "no_preguntado"} for name in ANAMNESIS_FIELDS}
    content.update(overrides)
    return content


# --- schema es el primer guardarraíl -------------------------------------


def test_schema_invalido_falla_antes_que_cualquier_otra_validacion():
    outcome = validate_generated_content(AIArtifactType.SUMMARY, {}, _TRANSCRIPT)
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED
    assert outcome.content is None


# --- respuesta evasiva -----------------------------------------------------


def test_respuesta_evasiva_se_rechaza():
    content = {"text": "Como modelo de lenguaje, no puedo generar contenido médico."}
    outcome = validate_generated_content(AIArtifactType.SUMMARY, content, _TRANSCRIPT)
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE


# --- grounding: clinical_flags es hoy el único tipo con source_excerpt -----


def test_clinical_flags_con_excerpt_grounded_construye_source_map():
    content = {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "Posible motivo de derivación.",
                "source_excerpt": "acúfenos en el oído izquierdo",
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, _TRANSCRIPT)
    assert outcome.ok is True
    assert outcome.source_map is not None
    assert outcome.source_map["flags[0]"]["excerpt"] == "acúfenos en el oído izquierdo"


def test_clinical_flags_con_excerpt_falso_se_rechaza_por_grounding():
    content = {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "d",
                "source_excerpt": "esto no aparece en la transcripción",
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, _TRANSCRIPT)
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED
    assert outcome.content is None


def test_clinical_flags_excerpt_ausente_null_no_bloquea_grounding():
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
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, _TRANSCRIPT)
    assert outcome.ok is True


def test_multiples_flags_todos_deben_estar_grounded():
    content = {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "d1",
                "source_excerpt": "acúfenos en el oído izquierdo",
                "ruleset_name": "demo_generic_v1",
            },
            {
                "category": "otalgia",
                "description": "d2",
                "source_excerpt": "frase inventada que no está",
                "ruleset_name": "demo_generic_v1",
            },
        ]
    }
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, _TRANSCRIPT)
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED


def test_transcript_vacio_rechaza_cualquier_excerpt_de_clinical_flags():
    content = {
        "flags": [
            {
                "category": "otalgia",
                "description": "d",
                "source_excerpt": "acúfenos",
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, "")
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED


# --- anamnesis: hoy sin source_excerpt -> grounding es un no-op ------------


def test_anamnesis_informado_sin_source_excerpt_no_activa_grounding_en_6_1():
    content = _anamnesis_content(
        **{ANAMNESIS_FIELDS[0]: {"value": "acúfenos", "status": "informado"}}
    )
    outcome = validate_generated_content(AIArtifactType.ANAMNESIS, content, _TRANSCRIPT)
    assert outcome.ok is True


def test_anamnesis_negado_explicitamente_sin_source_excerpt_no_activa_grounding_en_6_1():
    content = _anamnesis_content(
        **{ANAMNESIS_FIELDS[0]: {"value": "niega vértigo", "status": "negado_explicitamente"}}
    )
    outcome = validate_generated_content(AIArtifactType.ANAMNESIS, content, _TRANSCRIPT)
    assert outcome.ok is True


def test_anamnesis_no_preguntado_es_valido():
    content = _anamnesis_content(**{ANAMNESIS_FIELDS[0]: {"value": "", "status": "no_preguntado"}})
    outcome = validate_generated_content(AIArtifactType.ANAMNESIS, content, _TRANSCRIPT)
    assert outcome.ok is True


def test_anamnesis_no_determinado_es_valido():
    content = _anamnesis_content(
        **{ANAMNESIS_FIELDS[0]: {"value": "mención ambigua", "status": "no_determinado"}}
    )
    outcome = validate_generated_content(AIArtifactType.ANAMNESIS, content, _TRANSCRIPT)
    assert outcome.ok is True


# --- safety es el último guardarraíl de contenido --------------------------


def test_safety_bloquea_incluso_con_grounding_correcto():
    content = {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "El paciente tiene acúfenos confirmados.",
                "source_excerpt": "acúfenos en el oído izquierdo",
                "ruleset_name": "demo_generic_v1",
            }
        ]
    }
    outcome = validate_generated_content(AIArtifactType.CLINICAL_FLAGS, content, _TRANSCRIPT)
    assert outcome.ok is False
    assert outcome.failure_reason == AIGenerationFailureReason.SAFETY_POLICY_FAILED
    assert outcome.violated_rule_ids == ("el paciente tiene",)


def test_contenido_valido_pasa_las_cuatro_validaciones():
    outcome = validate_generated_content(
        AIArtifactType.SUMMARY, {"text": "Señal que requiere valoración profesional."}, _TRANSCRIPT
    )
    assert outcome.ok is True
    assert outcome.failure_reason is None
    assert outcome.content == {"text": "Señal que requiere valoración profesional."}
