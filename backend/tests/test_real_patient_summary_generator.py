"""Tests de RealPatientSummaryGenerator (Fase 6.3.6) — sin BD, sin
proveedor real."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.real_patient_summary_generator import RealPatientSummaryGenerator

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
        name="patient_summary_es_v1",
        version=1,
        description=None,
        system_prompt="Redacta en lenguaje llano.",
        user_prompt_template="Transcripción:\n$transcript\nResumen técnico:\n$summary_text",
        variables_schema={"required": ["transcript", "summary_text"], "optional": []},
        is_active=True,
        created_by=uuid.uuid4(),
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=AIArtifactType.PATIENT_SUMMARY,
        language="es",
    )


async def test_funciona_con_summary_text_vacio_dependencia_blanda():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"text": "explicación"}'))
    generator = RealPatientSummaryGenerator(provider, _template(), model="openai/gpt-5.2")

    draft = await generator.generate("transcripción", "", context=_CONTEXT)

    assert draft.text == "explicación"
    assert "transcripción" in provider.received_prompt.user
    assert "Resumen técnico:\n" in provider.received_prompt.user


async def test_incluye_el_summary_text_cuando_esta_disponible():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text='{"text": "explicación"}'))
    generator = RealPatientSummaryGenerator(provider, _template(), model="openai/gpt-5.2")

    await generator.generate("transcripción", "resumen técnico real", context=_CONTEXT)

    assert "resumen técnico real" in provider.received_prompt.user


async def test_json_invalido_lanza_transient_provider_error():
    provider = _FakeLanguageModelProvider(LanguageModelResponse(text="no-json"))
    generator = RealPatientSummaryGenerator(provider, _template(), model="openai/gpt-5.2")

    with pytest.raises(TransientProviderError) as exc_info:
        await generator.generate("transcripción", "", context=_CONTEXT)
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
