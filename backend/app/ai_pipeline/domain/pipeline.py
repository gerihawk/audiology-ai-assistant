"""Orquestador del AI Pipeline y contrato de cada paso.

`PipelineStep` y `PipelineOrchestrator` son puertos (Protocol):
completamente desacoplados de cualquier proveedor concreto, solo conocen
las interfaces de `integrations/domain/`. Ningún paso ni el orquestador
tocan la base de datos — devuelven `PipelineStepOutcome`/`PipelineResult`
en memoria; la persistencia (artefactos, versiones, auditoría) es
responsabilidad exclusiva de `AIPipelineService` (ver
docs/ai-pipeline-architecture.md §5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True)
class PipelineExecutionContext:
    """Estado mutable de una ejecución del pipeline: la sesión sobre la que
    se ejecuta y las salidas ya producidas por pasos anteriores, indexadas
    por tipo de artefacto, para que un paso pueda consumir la salida de
    otro sin que ninguno conozca al resto del grafo."""

    clinical_session_id: uuid.UUID
    session_context: SessionContext
    outputs: dict[AIArtifactType, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineStepOutcome:
    """Resultado de un paso — no persistido, DTO en memoria.

    `status is None` significa que el paso se saltó (nunca se invocó,
    porque una dependencia falló o se saltó a su vez) — distinto de
    `FAILED` (se invocó y el proveedor falló). Ver
    docs/ai-pipeline-architecture.md §8."""

    artifact_type: AIArtifactType
    status: AIGenerationRunStatus | None
    content: dict[str, Any] | None
    confidence: int | None
    provider_name: str | None
    model_name: str | None
    input_token_count: int | None
    output_token_count: int | None
    estimated_cost_usd: Decimal | None
    latency_ms: int | None
    execution_time_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    skipped_reason: str | None


@dataclass(slots=True)
class PipelineResult:
    outcomes: list[PipelineStepOutcome]


class PipelineStep(Protocol):
    artifact_type: AIArtifactType

    def depends_on(self) -> frozenset[AIArtifactType]:
        """Qué otros `artifact_type` deben haber completado antes de este
        paso. Permite que un futuro orquestador paralelo decida el orden
        sin que el paso lo sepa — ver docs/ai-pipeline-architecture.md §1.4."""
        ...

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome: ...


class PipelineOrchestrator(Protocol):
    async def run(
        self, context: PipelineExecutionContext, steps: list[PipelineStep]
    ) -> PipelineResult: ...


class SequentialPipelineOrchestrator:
    """Implementación por defecto: ejecuta `steps` en el orden recibido
    (una ordenación topológica válida del grafo, responsabilidad de quien
    construye la lista — ver `PIPELINE_STEP_ORDER`), de forma síncrona.

    Sin colas, workers ni procesamiento distribuido (decisión cerrada de
    esta fase). Un futuro orquestador paralelo que respete
    `depends_on()` es un reemplazo de esta clase sin tocar ningún
    `PipelineStep`.
    """

    async def run(
        self, context: PipelineExecutionContext, steps: list[PipelineStep]
    ) -> PipelineResult:
        outcomes: list[PipelineStepOutcome] = []
        failed_or_skipped: set[AIArtifactType] = set()

        for step in steps:
            blocking = step.depends_on() & failed_or_skipped
            if blocking:
                blocking_names = ", ".join(sorted(t.value for t in blocking))
                outcomes.append(
                    PipelineStepOutcome(
                        artifact_type=step.artifact_type,
                        status=None,
                        content=None,
                        confidence=None,
                        provider_name=None,
                        model_name=None,
                        input_token_count=None,
                        output_token_count=None,
                        estimated_cost_usd=None,
                        latency_ms=None,
                        execution_time_ms=None,
                        started_at=None,
                        completed_at=None,
                        failure_reason=None,
                        skipped_reason=(
                            f"Dependencia(s) no disponible(s) en esta ejecución: {blocking_names}."
                        ),
                    )
                )
                failed_or_skipped.add(step.artifact_type)
                continue

            outcome = await step.run(context)
            outcomes.append(outcome)
            if outcome.status == AIGenerationRunStatus.FAILED:
                failed_or_skipped.add(step.artifact_type)
            elif outcome.status == AIGenerationRunStatus.COMPLETED:
                context.outputs[step.artifact_type] = outcome.content

        return PipelineResult(outcomes=outcomes)
