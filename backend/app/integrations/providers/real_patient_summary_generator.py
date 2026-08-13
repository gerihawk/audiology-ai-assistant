"""RealPatientSummaryGenerator (Fase 6.3.6) — mismo patrón que
RealSummaryGenerator, ver ese módulo para el detalle del flujo.
`summary_text` puede ser cadena vacía (RFC §4.3, dependencia blanda con
`SUMMARY`) — la plantilla `patient_summary_es_v1` ya declara esa variable
como obligatoria pero tolera vacío (ver
`app/ai_pipeline/prompts/patient_summary_es_v1.md`)."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import PromptTemplate, RenderContext
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.prompt_renderer import PromptRenderer
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.patient_summary_generator import PatientSummaryDraft
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.json_response import parse_json_object

_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


class RealPatientSummaryGenerator:
    def __init__(
        self,
        provider: LanguageModelProvider,
        template: PromptTemplate,
        *,
        model: str,
        renderer: PromptRenderer | None = None,
    ) -> None:
        self._provider = provider
        self._template = template
        self._model = model
        self._renderer = renderer or PromptRenderer()

    async def generate(
        self, transcript: str, summary_text: str, *, context: SessionContext
    ) -> PatientSummaryDraft:
        rendered = self._renderer.render(
            self._template,
            RenderContext(variables={"transcript": transcript, "summary_text": summary_text}),
        )
        response = await self._provider.complete(
            RenderedPrompt(system=rendered.system_prompt, user=rendered.user_prompt),
            model=self._model,
            response_json_schema=_RESPONSE_JSON_SCHEMA,
        )
        content = parse_json_object(response.text)
        text = content.get("text")
        if not isinstance(text, str):
            raise TransientProviderError(
                "La respuesta del proveedor no incluye un campo 'text' de tipo string.",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        return PatientSummaryDraft(
            text=text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reasoning_tokens=response.reasoning_tokens,
        )
