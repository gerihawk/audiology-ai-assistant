"""Puerto ClinicalFlagsGenerator.

Sustituye y absorbe a la antigua interfaz `ClinicalFlagRuleset` (ver
docs/ai-pipeline-architecture.md §6.1 y §12 decisión 18). A diferencia de
`SummaryGenerator`/`MissingInformationGenerator`/`AnamnesisGenerator`, una
implementación de esta interfaz **no está obligada** a componer
`LanguageModelProvider`: la implementación de referencia
(`MockClinicalFlagsGenerator`) es deliberadamente un checklist basado en
reglas, sin LLM — decisión de seguridad clínica ya cerrada en
docs/clinical-safety.md §7, no revertida aquí.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True, frozen=True)
class ClinicalFlagDraft:
    category: str
    description: str
    source_excerpt: str | None
    ruleset_name: str


class ClinicalFlagsGenerator(Protocol):
    async def generate(
        self, transcript: str, *, context: SessionContext
    ) -> list[ClinicalFlagDraft]: ...
