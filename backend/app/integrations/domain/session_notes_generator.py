"""Puerto SessionNotesGenerator — Fase 6.4.3, RFC técnico de 6.4 §8.

`AIArtifactType.SESSION_NOTES`: documenta una visita posterior cuando el
paciente ya tiene una `ANAMNESIS` aprobada de otra sesión — nunca compite
con `ANAMNESIS` en la misma ejecución (mutuamente excluyentes vía
`applies_to()`, ver `ai_pipeline/domain/steps/session_notes_step.py` y
`anamnesis_step.py`).

`SESSION_NOTES_BLOCKS` son los 4 bloques cerrados del contrato (RFC
§4.7): ninguno es un enum de estado como en ANAMNESIS — la única señal de
"no explorado" es `text=""`/`source_excerpt=None`.

`previous_anamnesis_context: str | None` es deliberadamente un `str`
plano, no un `PreviousAnamnesisRef` de `ai_pipeline.domain.patient_context`:
este módulo (`integrations/domain/`) nunca importa tipos de `ai_pipeline/`
— es `ai_pipeline/domain/steps/session_notes_step.py` quien conoce ambos
lados y hace la conversión, preservando la dirección de dependencia
existente (`ai_pipeline` → `integrations`, nunca al revés). El contexto
previo ayuda a interpretar referencias, pero nunca es evidencia de que
algo se haya dicho en la sesión actual — solo `transcript` puede
satisfacer `source_excerpt` (RFC técnico §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.session_context import SessionContext

SESSION_NOTES_BLOCKS: tuple[str, ...] = (
    "changes_since_last_visit",
    "device_adjustments",
    "patient_reported_issues",
    "next_steps",
)


@dataclass(slots=True, frozen=True)
class SessionNotesBlock:
    text: str
    source_excerpt: str | None = None


@dataclass(slots=True, frozen=True)
class SessionNotesDraft:
    blocks: dict[str, SessionNotesBlock]


class SessionNotesGenerator(Protocol):
    async def generate(
        self,
        transcript: str,
        previous_anamnesis_context: str | None,
        *,
        context: SessionContext,
    ) -> SessionNotesDraft: ...
