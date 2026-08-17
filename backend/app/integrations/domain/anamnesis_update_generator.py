"""Puerto AnamnesisUpdateGenerator — Hito 6.5.2, RFC técnico de 6.5 §2-§3.

`AnamnesisFieldUpdate`/`AnamnesisUpdateReason` viven aquí, no en
`ai_pipeline/domain/anamnesis_update.py` (donde se introdujeron en 6.5.1):
son vocabulario de "lo que produce un generator", igual que
`AnamnesisFieldValue`/`AnamnesisDraft` (`anamnesis_generator.py`) o
`MissingInfoItem`/`MissingInformationResult`
(`missing_information_generator.py`) — `integrations/domain/` nunca
importa tipos de `ai_pipeline/` (mismo principio ya aplicado por
`session_notes_generator.py` con `PreviousAnamnesisRef`). Reubicación
mecánica: mismos nombres, mismos campos, mismo comportamiento;
`ai_pipeline/domain/anamnesis_update.py` los reimporta y reexporta, así
que ningún call site de 6.5.1 cambia.

El generator **interpreta lenguaje** — decide si una frase llena un hueco
o corrige explícitamente un valor previo, qué campo corresponde, el
`proposed_value`/`proposed_status`/`source_excerpt` y el `reason`. NO es
responsable de persistir, aprobar, construir `AIArtifact`, decidir stale
baseline, ni de la validación final (eso sigue siendo autoridad exclusiva
de `validate_update_batch`/`verify_update_grounding`/`materialize_anamnesis`,
`ai_pipeline/domain/anamnesis_update.py`, 6.5.1) — un generator solo
PROPONE, nunca valida de forma autoritativa."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus
from app.integrations.domain.session_context import SessionContext


class AnamnesisUpdateReason(StrEnum):
    FILLS_GAP = "fills_gap"
    EXPLICIT_CORRECTION = "explicit_correction"


@dataclass(slots=True, frozen=True)
class AnamnesisFieldUpdate:
    """Un cambio propuesto sobre un único campo de ANAMNESIS — estructura
    interna de dominio para representar el diff, nunca persistida tal
    cual."""

    field_name: str
    previous_value: str
    previous_status: AnamnesisFieldStatus
    proposed_value: str
    proposed_status: AnamnesisFieldStatus
    source_excerpt: str
    reason: AnamnesisUpdateReason


@dataclass(slots=True, frozen=True)
class AnamnesisUpdateResult:
    """Envelope del resultado completo de una generación — mismo criterio
    que `MissingInformationResult`: el usage real del proveedor es un dato
    de la llamada completa, no de cada `AnamnesisFieldUpdate` individual.
    `input_tokens`/`output_tokens`/`reasoning_tokens` quedan `None` en el
    Mock (sin proveedor real en 6.5, ver RFC técnico de 6.5 §16) — listos
    para cuando exista un `RealAnamnesisUpdateGenerator`, sin cambiar esta
    forma."""

    updates: list[AnamnesisFieldUpdate]
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None


class AnamnesisUpdateGenerator(Protocol):
    """`previous_anamnesis` es el mismo `dict` plano persistido en
    `AIArtifactVersion.content` (forma cerrada de ANAMNESIS, ver
    `ai_pipeline/domain/schemas.py`) — nunca un `PreviousAnamnesisRef` de
    `ai_pipeline.domain.patient_context` (misma razón que
    `SessionNotesGenerator.previous_anamnesis_context`: este módulo nunca
    importa tipos de `ai_pipeline/`). `transcript` y `previous_anamnesis`
    son entradas separadas por firma de tipos — evidencia citable
    (`source_excerpt`) solo puede proceder de `transcript`, nunca de
    `previous_anamnesis` (RFC técnico de 6.5, Decisión 1/§11)."""

    async def generate(
        self,
        transcript: str,
        previous_anamnesis: dict[str, Any],
        *,
        context: SessionContext,
    ) -> AnamnesisUpdateResult: ...
