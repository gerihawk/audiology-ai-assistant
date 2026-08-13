"""Puerto SummaryGenerator. Ver docs/ai-pipeline-architecture.md §6.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True, frozen=True)
class SummaryDraft:
    text: str
    #: Usage real del proveedor (Fase 6.3) — `None` en `MockSummaryGenerator`.
    #: Ver docs/fase-6-rfc.md §6.3 y `steps/base.py::ProduceResult`.
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Tokens de razonamiento facturables, separados de `output_tokens`
    #: (Google Gemini únicamente hoy) — ver
    #: `LanguageModelResponse.reasoning_tokens`.
    reasoning_tokens: int | None = None


class SummaryGenerator(Protocol):
    async def generate(self, transcript: str, *, context: SessionContext) -> SummaryDraft: ...
