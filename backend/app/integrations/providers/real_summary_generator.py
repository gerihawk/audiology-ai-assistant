"""RealSummaryGenerator: primer Generator real del AI Pipeline (Fase 6.3.6).

Compone `PromptTemplate` (ya resuelto por `AIPipelineService` antes de
construir los steps — nunca toca BD, ver docs/fase-6-rfc.md §10 hito
6.3.3) + `PromptRenderer` (determinista, tampoco toca BD) +
`LanguageModelProvider` inyectado (agnóstico de cuál sea, RFC §7.2). Nunca
conoce `AsyncSession`, ningún repositorio, ni el SDK/HTTP concreto del
vendor detrás del `LanguageModelProvider`.

Flujo: transcript -> RenderContext -> PromptRenderer.render() ->
LanguageModelProvider.complete() -> json.loads() -> SummaryDraft.
"""

from __future__ import annotations

from app.ai_pipeline.domain.entities import PromptTemplate, RenderContext
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.prompt_renderer import PromptRenderer
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.summary_generator import SummaryDraft
from app.integrations.providers.json_response import parse_json_object

#: Usado solo cuando el proveedor soporta salida estructurada real (Fase
#: 6.3.5) — la respuesta se valida igual después con
#: `validate_content_schema`, nunca se confía en que el proveedor lo
#: cumplió (RFC §7.2).
_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


class RealSummaryGenerator:
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

    async def generate(self, transcript: str, *, context: SessionContext) -> SummaryDraft:
        rendered = self._renderer.render(
            self._template, RenderContext(variables={"transcript": transcript})
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
        return SummaryDraft(
            text=text, input_tokens=response.input_tokens, output_tokens=response.output_tokens
        )
