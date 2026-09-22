"""Puerto ClinicalFlagsGenerator.

Sustituye y absorbe a la antigua interfaz `ClinicalFlagRuleset` (ver
docs/ai-pipeline-architecture.md §6.1 y §12 decisión 18). A diferencia de
`SummaryGenerator`/`MissingInformationGenerator`/`AnamnesisGenerator`, una
implementación de esta interfaz **no está obligada** a componer
`LanguageModelProvider`: la implementación de referencia
(`MockClinicalFlagsGenerator`) es deliberadamente un checklist basado en
reglas, sin LLM.

Ampliación 2026-09-21 (docs/clinical-safety.md §7): esa decisión de
seguridad clínica se reabrió deliberadamente y ahora existe también
`RealClinicalFlagsGenerator` (`app/integrations/providers/`), que sí
compone `LanguageModelProvider`. Sigue sin ser la implementación por
defecto en ningún entorno — `Settings.llm_provider_clinical_flags`
("mock" por defecto siempre) decide cuál de las dos usa
`AIPipelineService`, y activar la real para cualquier clínica exige la
validación clínica y legal que ese documento pide.
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
