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

from app.ai_pipeline.domain.cost_budget import SessionCostBudget
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.retry_policy import RetryConfig
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.transcription_provider import AudioForTranscription

#: Techo de tokens de salida para la estimación "peor caso razonable"
#: previa a la llamada (§6.3) cuando no se recibe uno explícito desde
#: `Settings` — ver `AIPipelineService`.
DEFAULT_MAX_OUTPUT_TOKENS_ESTIMATE = 2000


@dataclass(slots=True)
class PipelineExecutionContext:
    """Estado mutable de una ejecución del pipeline: la sesión sobre la que
    se ejecuta y las salidas ya producidas por pasos anteriores, indexadas
    por tipo de artefacto, para que un paso pueda consumir la salida de
    otro sin que ninguno conozca al resto del grafo.

    `audio_input` (Fase 5) es `None` en `run_pipeline` (Mock Pipeline,
    comportamiento sin cambios): solo `AIPipelineService.transcribe_from_audio`
    lo rellena, con los bytes ya leídos de `AudioStorage` — ver
    `TranscriptionStep.run`.

    `cost_budget`/`retry_config`/`max_output_tokens_estimate` (Fase 6.1)
    son la única vía por la que `run_provider_step` conoce los guardarraíles
    de runtime — resueltos una vez por `AIPipelineService` desde
    `Settings`/BD, nunca leídos directamente por un `PipelineStep` (que
    sigue sin tocar BD, ver docs/fase-6-rfc.md §5). `cost_budget=None`
    (valor por defecto) desactiva el límite de coste — mismo criterio que
    `Settings.llm_cost_limit_enforced=False`."""

    clinical_session_id: uuid.UUID
    session_context: SessionContext
    outputs: dict[AIArtifactType, Any] = field(default_factory=dict)
    audio_input: AudioForTranscription | None = None
    cost_budget: SessionCostBudget | None = None
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    max_output_tokens_estimate: int = DEFAULT_MAX_OUTPUT_TOKENS_ESTIMATE


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
    #: Metadata segura ya extraída del proveedor (Fase 5.1) — nunca el
    #: `raw_response` completo. `None` salvo en `TranscriptionStep` con un
    #: proveedor que la aporta (ver
    #: docs/transcription-benchmark.md §Model traceability). Se persiste
    #: en `AIGenerationRun.raw_response`.
    provider_metadata: dict[str, Any] | None = None
    #: JSONB top-level de `AIArtifactVersion` (Fase 6.1) — agregado por
    #: `validation_pipeline.py` a partir de los `source_excerpt` ya
    #: validados contra el transcript, nunca aportado por el proveedor
    #: como autoridad (ver docs/fase-6-rfc.md §5.4). `None` si el
    #: artefacto no declara ningún campo con evidencia.
    source_map: dict[str, Any] | None = None


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
