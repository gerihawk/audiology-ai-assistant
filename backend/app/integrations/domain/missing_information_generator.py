"""Puerto MissingInformationGenerator.

Depende del resumen y de las señales de alerta, no de la anamnesis — la
anamnesis todavía no existe en este punto del pipeline. Ver
docs/ai-pipeline-architecture.md §1.4 y §6.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True, frozen=True)
class MissingInfoItem:
    topic: str
    suggested_question: str


class MissingInformationGenerator(Protocol):
    async def generate(
        self,
        summary: str,
        clinical_flags: list[ClinicalFlagDraft],
        *,
        context: SessionContext,
    ) -> list[MissingInfoItem]: ...
