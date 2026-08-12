"""Tests de RealMissingInformationGenerator (Fase 6.3.6) — sin BD, sin
proveedor real."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.language_model_provider import LanguageModelResponse
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.real_missing_information_generator import (
    RealMissingInformationGenerator,
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
        name="missing_information_es_v1",
        version=1,
        description=None,
        system_prompt="Identifica información ausente.",
        user_prompt_template="Resumen:\n$summary_text\nSeñales:\n$clinical_flags_text",
        variables_schema={"required": ["summary_text", "clinical_flags_text"], "optional": []},
        is_active=True,
        created_by=uuid.uuid4(),
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=AIArtifactType.MISSING_INFORMATION,
        language="es",
    )


_VALID_RESPONSE = (
    '{"items": [{"topic": "antecedentes_familiares", '
    '"suggested_question": "¿Hay antecedentes familiares?"}]}'
)


async def test_json_valido_produce_items_con_usage():
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(text=_VALID_RESPONSE, input_tokens=20, output_tokens=6)
    )
    generator = RealMissingInformationGenerator(provider, _template(), model="claude-opus-5")

    result = await generator.generate("resumen", [], context=_CONTEXT)

    assert len(result.items) == 1
    assert result.items[0].topic == "antecedentes_familiares"
    assert result.input_tokens == 20
    assert result.output_tokens == 6


async def test_sin_flags_usa_texto_explicito_de_ausencia():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text=_VALID_RESPONSE))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")

    await generator.generate("resumen", [], context=_CONTEXT)

    assert "Sin señales de alerta detectadas." in provider.received_prompt.user


async def test_con_flags_los_incluye_como_texto_legible():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text=_VALID_RESPONSE))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")
    flags = [
        ClinicalFlagDraft(
            category="tinnitus_unilateral",
            description="Posible motivo de derivación.",
            source_excerpt="me pita el oído",
            ruleset_name="demo",
        )
    ]

    await generator.generate("resumen", flags, context=_CONTEXT)

    assert "tinnitus_unilateral: Posible motivo de derivación." in provider.received_prompt.user
    # El source_excerpt nunca se filtra al prompt de este step (ver docstring).
    assert "me pita el oído" not in provider.received_prompt.user


async def test_items_vacio_es_valido():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"items": []}'))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")

    result = await generator.generate("resumen", [], context=_CONTEXT)

    assert result.items == []


async def test_json_invalido_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text="no-json"))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("resumen", [], context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_items_no_es_lista_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"items": "no-list"}'))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("resumen", [], context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_item_con_forma_incorrecta_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"items": [{"topic": 1}]}'))
    generator = RealMissingInformationGenerator(provider, _template(), model="m")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("resumen", [], context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
