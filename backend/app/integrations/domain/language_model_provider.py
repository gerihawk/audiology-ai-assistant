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
from typing import Protocol


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


class LanguageModelProvider(Protocol):
    async def complete(
        self, prompt: RenderedPrompt, *, model: str | None = None
    ) -> LanguageModelResponse: ...
