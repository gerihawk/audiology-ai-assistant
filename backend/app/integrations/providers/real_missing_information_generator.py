"""RealMissingInformationGenerator (Fase 6.3.6) — mismo patrón que
RealSummaryGenerator, ver ese módulo para el detalle del flujo.

La plantilla `missing_information_es_v1` declara `clinical_flags_text`
como variable obligatoria (texto, ver
`app/ai_pipeline/prompts/missing_information_es_v1.md`), pero
`ClinicalFlagsStep` produce una lista estructurada de `ClinicalFlagDraft`
— no existe una convención previa en el repositorio para volcar esa lista
a texto (el benchmark de la Fase 6.2 usa un fixture de dataset ya en
texto, nunca deriva de `ClinicalFlagDraft`). `_format_clinical_flags` es
la única responsable de esa conversión, deliberadamente simple: una línea
por señal con su categoría y descripción, nunca el `source_excerpt`
(evitar filtrar contenido de la transcripción actual dos veces por rutas
distintas de un mismo prompt)."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import PromptTemplate, RenderContext
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.prompt_renderer import PromptRenderer
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.missing_information_generator import (
    MissingInfoItem,
    MissingInformationResult,
)
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.json_response import parse_json_object

_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "suggested_question": {"type": "string"},
                },
                "required": ["topic", "suggested_question"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_NO_FLAGS_TEXT = "Sin señales de alerta detectadas."


def _format_clinical_flags(clinical_flags: list[ClinicalFlagDraft]) -> str:
    if not clinical_flags:
        return _NO_FLAGS_TEXT
    return "\n".join(f"- {flag.category}: {flag.description}" for flag in clinical_flags)


class RealMissingInformationGenerator:
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
        self,
        summary: str,
        clinical_flags: list[ClinicalFlagDraft],
        *,
        context: SessionContext,
    ) -> MissingInformationResult:
        rendered = self._renderer.render(
            self._template,
            RenderContext(
                variables={
                    "summary_text": summary,
                    "clinical_flags_text": _format_clinical_flags(clinical_flags),
                }
            ),
        )
        response = await self._provider.complete(
            RenderedPrompt(system=rendered.system_prompt, user=rendered.user_prompt),
            model=self._model,
            response_json_schema=_RESPONSE_JSON_SCHEMA,
        )
        content = parse_json_object(response.text)
        items = _parse_items(content.get("items"))
        return MissingInformationResult(
            items=items,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reasoning_tokens=response.reasoning_tokens,
        )


def _parse_items(raw_items: object) -> list[MissingInfoItem]:
    if not isinstance(raw_items, list):
        raise TransientProviderError(
            "La respuesta del proveedor no incluye un campo 'items' de tipo lista.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )
    items: list[MissingInfoItem] = []
    for raw_item in raw_items:
        if (
            not isinstance(raw_item, dict)
            or not isinstance(raw_item.get("topic"), str)
            or not isinstance(raw_item.get("suggested_question"), str)
        ):
            raise TransientProviderError(
                "Un elemento de 'items' no tiene la forma esperada "
                "(topic/suggested_question de tipo string).",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        items.append(
            MissingInfoItem(
                topic=raw_item["topic"], suggested_question=raw_item["suggested_question"]
            )
        )
    return items
