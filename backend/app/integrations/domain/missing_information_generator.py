"""Puerto MissingInformationGenerator.

Depende del resumen y de las señales de alerta, no de la anamnesis — la
anamnesis todavía no existe en este punto del pipeline. Ver
docs/ai-pipeline-architecture.md §1.4 y §6.1.

`MissingInformationTarget` (Fase 6.4.4, RFC técnico de 6.4 §10): el
esquema objetivo contra el que se evalúan los gaps — decidido siempre por
código (`ai_pipeline.domain.patient_context.resolve_missing_information_target`),
nunca por el LLM/Mock. Vive en `integrations/domain/`, no en
`ai_pipeline/domain/patient_context.py`: este `Protocol` necesita
referenciarlo en la firma de `generate()`, y `integrations/domain/` nunca
importa tipos de `ai_pipeline/` (mismo principio ya aplicado por
`session_notes_generator.py` con `PreviousAnamnesisRef` — evita invertir
la dirección de dependencia `ai_pipeline` → `integrations`). El JSON
generado (`items`) no incluye el target — es contexto de ejecución, no
parte del artefacto clínico.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.session_context import SessionContext


class MissingInformationTarget(StrEnum):
    ANAMNESIS_FIELDS = "anamnesis_fields"
    SESSION_NOTES_BLOCKS = "session_notes_blocks"


@dataclass(slots=True, frozen=True)
class MissingInfoItem:
    topic: str
    suggested_question: str


@dataclass(slots=True, frozen=True)
class MissingInformationResult:
    """Envelope del resultado completo de una generación — a diferencia de
    `SummaryDraft`/`AnamnesisDraft`, este generator no tenía un objeto
    contenedor propio (devolvía `list[MissingInfoItem]` directamente); se
    introduce aquí porque el usage real del proveedor (Fase 6.3) es un dato
    de la llamada completa, no de cada item individual."""

    items: list[MissingInfoItem]
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Tokens de razonamiento facturables, separados de `output_tokens`
    #: (Google Gemini únicamente hoy) — ver
    #: `LanguageModelResponse.reasoning_tokens`.
    reasoning_tokens: int | None = None


class MissingInformationGenerator(Protocol):
    async def generate(
        self,
        summary: str,
        clinical_flags: list[ClinicalFlagDraft],
        *,
        target: MissingInformationTarget,
        context: SessionContext,
    ) -> MissingInformationResult: ...
