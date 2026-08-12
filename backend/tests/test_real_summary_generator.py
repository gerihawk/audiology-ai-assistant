"""Tests de RealSummaryGenerator (Fase 6.3.6) — sin BD, sin proveedor
real: el `LanguageModelProvider` es un doble en memoria."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.real_summary_generator import RealSummaryGenerator

_CONTEXT = SessionContext(clinical_session_id=uuid.uuid4())


class _FakeLanguageModelProvider:
    def __init__(self, response: LanguageModelResponse) -> None:
        self.received_prompt = None
        self.received_model = None
        self.received_schema = None
        self._response = response

    async def complete(self, prompt, *, model=None, response_json_schema=None):
        self.received_prompt = prompt
        self.received_model = model
        self.received_schema = response_json_schema
        return self._response


def _template() -> PromptTemplate:
    return PromptTemplate(
        id=uuid.uuid4(),
        name="summary_es_v1",
        version=1,
        description=None,
        system_prompt="Eres un asistente clínico.",
        user_prompt_template="Transcripción:\n$transcript",
        variables_schema={"required": ["transcript"], "optional": []},
        is_active=True,
        created_by=uuid.uuid4(),
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=AIArtifactType.SUMMARY,
        language="es",
    )


async def test_renderiza_la_plantilla_con_el_transcript():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"text": "resumen"}'))
    generator = RealSummaryGenerator(provider, _template(), model="claude-opus-5")

    await generator.generate("El paciente refiere acúfenos.", context=_CONTEXT)

    assert provider.received_model == "claude-opus-5"
    assert "El paciente refiere acúfenos." in provider.received_prompt.user
    assert provider.received_prompt.system == "Eres un asistente clínico."
    assert provider.received_schema is not None
    assert provider.received_schema["required"] == ["text"]


async def test_json_valido_produce_summary_draft_con_usage():
    provider = _FakeLanguageModelProvider(
        LanguageModelResponse(text='{"text": "resumen generado"}', input_tokens=50, output_tokens=8)
    )
    generator = RealSummaryGenerator(provider, _template(), model="claude-opus-5")

    draft = await generator.generate("transcripción", context=_CONTEXT)

    assert draft.text == "resumen generado"
    assert draft.input_tokens == 50
    assert draft.output_tokens == 8


async def test_json_invalido_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text="esto no es JSON"))
    generator = RealSummaryGenerator(provider, _template(), model="claude-opus-5")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_json_sin_campo_text_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"other": "value"}'))
    generator = RealSummaryGenerator(provider, _template(), model="claude-opus-5")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_json_con_text_de_tipo_incorrecto_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"text": 123}'))
    generator = RealSummaryGenerator(provider, _template(), model="claude-opus-5")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
