"""Tests de RealClinicalFlagsGenerator (ampliación 2026-09-21,
docs/clinical-safety.md §7) — sin BD, sin proveedor real. Cubre el
parseo/validación estructural que hace el propio generador; el grounding
contra la transcripción real y el filtro de lenguaje prohibido los cubre
`validate_generated_content` (ver test_ai_pipeline_clinical_flags_step.py
y test_ai_pipeline_llm_routing.py para la integración completa)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.real_clinical_flags_generator import (
    RULESET_NAME,
    RealClinicalFlagsGenerator,
)

_CONTEXT = SessionContext(clinical_session_id=uuid.uuid4())


class _FakeLanguageModelProvider:
    def __init__(self, response: LanguageModelResponse) -> None:
        self.received_prompt = None
        self._response = response

    async def complete(self, prompt, *, model=None, response_json_schema=None):
        self.received_prompt = prompt
        return self._response


def _template() -> PromptTemplate:
    return PromptTemplate(
        id=uuid.uuid4(),
        name="clinical_flags_es_v1",
        version=1,
        description=None,
        system_prompt="Detecta señales de alerta.",
        user_prompt_template="Transcripción:\n$transcript",
        variables_schema={"required": ["transcript"], "optional": []},
        is_active=True,
        created_by=uuid.uuid4(),
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=AIArtifactType.CLINICAL_FLAGS,
        language="es",
    )


_VALID_RESPONSE = (
    '{"flags": [{"category": "tinnitus_unilateral", '
    '"description": "Señal que requiere valoración profesional.", '
    '"source_excerpt": "me pita mucho el oído izquierdo"}]}'
)


async def test_json_valido_produce_flags_con_ruleset_name_fijo():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text=_VALID_RESPONSE))
    generator = RealClinicalFlagsGenerator(provider, _template(), model="claude-opus-5")

    flags = await generator.generate("me pita mucho el oído izquierdo", context=_CONTEXT)

    assert len(flags) == 1
    assert flags[0].category == "tinnitus_unilateral"
    assert flags[0].source_excerpt == "me pita mucho el oído izquierdo"
    # `ruleset_name` nunca lo decide el LLM — es una constante de código.
    assert flags[0].ruleset_name == RULESET_NAME == "clinical_flags_llm_es_v1"


async def test_flags_vacio_es_valido():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"flags": []}'))
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    flags = await generator.generate("transcripción sin señales", context=_CONTEXT)

    assert flags == []


async def test_transcript_llega_al_prompt_renderizado():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"flags": []}'))
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    await generator.generate("texto de la transcripción de hoy", context=_CONTEXT)

    assert "texto de la transcripción de hoy" in provider.received_prompt.user


async def test_json_invalido_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text="no-json"))
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_flags_no_es_lista_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"flags": "no-list"}'))
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_flag_con_forma_incorrecta_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(text='{"flags": [{"category": "otalgia"}]}')
    )
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_source_excerpt_vacio_lanza_transient_provider_error():
    """Nunca se acepta una señal 'sin evidencia todavía' — a diferencia del
    schema general de `ClinicalFlagDraft` (source_excerpt nullable), este
    generador exige una cita no vacía en cada señal que reporte."""
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(
            text='{"flags": [{"category": "otalgia", "description": "desc", '
            '"source_excerpt": "   "}]}'
        )
    )
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_category_con_formato_invalido_lanza_transient_provider_error():
    """`category` debe ser un identificador snake_case corto, nunca una
    frase — protege la auditabilidad del checklist frente a un LLM que
    devuelva texto libre en ese campo."""
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(
            text='{"flags": [{"category": "El paciente tiene otalgia", '
            '"description": "desc", "source_excerpt": "me duele el oído"}]}'
        )
    )
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_description_vacia_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(
            text='{"flags": [{"category": "otalgia", "description": "", '
            '"source_excerpt": "me duele el oído"}]}'
        )
    )
    generator = RealClinicalFlagsGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
