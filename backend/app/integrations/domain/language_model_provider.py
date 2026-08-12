"""Puerto LanguageModelProvider — interfaz de bajo nivel.

Es la única interfaz de este bloque que implementaría directamente un SDK
de proveedor real (OpenAI, Anthropic, Gemini, Ollama...). `SummaryGenerator`,
`MissingInformationGenerator` y `AnamnesisGenerator` la componen, no la
sustituyen — ver docs/ai-pipeline-architecture.md §6.1 y §7.2.
`ClinicalFlagsGenerator` es la excepción deliberada (basado en reglas, sin
LLM) y no depende de esta interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class RenderedPrompt:
    """Resultado de `PromptRenderer.render(...)`. En esta fase (4.1) los
    `Mock*Generator` construyen esto directamente, sin pasar por
    `PromptTemplate`/`PromptRenderer` (infraestructura todavía no cargada
    con prompts reales — ver docs/development-plan.md Fase 4.7)."""

    system: str | None
    user: str


@dataclass(slots=True, frozen=True)
class LanguageModelResponse:
    text: str
    #: Uso real reportado por el proveedor (Fase 6.3), cuando la API lo
    #: expone. `None` en `MockLanguageModelProvider` y en cualquier
    #: proveedor que no lo reporte — `run_provider_step` cae entonces al
    #: `TokenCounter` heurístico, nunca al revés (un usage real nunca se
    #: sustituye por una estimación).
    input_tokens: int | None = None
    output_tokens: int | None = None


class LanguageModelProvider(Protocol):
    async def complete(
        self,
        prompt: RenderedPrompt,
        *,
        model: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> LanguageModelResponse:
        """`response_json_schema` (Fase 6.3.5, extensión aditiva — mismo
        criterio ya usado en `benchmark/generation/openrouter_client.py::
        LlmCompletionRequest.response_json_schema`): JSON Schema opcional
        para pedir salida estructurada cuando el proveedor real lo soporte
        de verdad (verificado contra su documentación oficial, nunca
        supuesto por lo observado en OpenRouter — ver
        docs/fase-6-rfc.md §11.2). El adapter solo reenvía el schema al
        wire format del vendor: no interpreta su contenido ni decide cuál
        usar — esa decisión es del `Generator` (eje del artefacto), nunca
        del proveedor (eje del vendor), ver §7.2. Un proveedor que lo
        soporte lo usa; uno que no, lo ignora — la respuesta se valida
        igual con `validate_content_schema` después, nunca se confía en
        que el proveedor cumplió el schema."""
        ...
