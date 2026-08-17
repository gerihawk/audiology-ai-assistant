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
from enum import StrEnum
from typing import Any, Protocol

from app.ai_pipeline.domain.cost_budget import SessionCostBudget
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.patient_context import LoadedPatientContext, PatientContextRequirement
from app.ai_pipeline.domain.retry_policy import RetryConfig
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.transcription_provider import AudioForTranscription


class SkipReasonCode(StrEnum):
    """Motivo tipado de un `PipelineStepOutcome` con `status=None` — nunca
    se mezcla con `AIGenerationFailureReason` (ese enum es exclusivamente
    para `FAILED`, ver `errors.py`; un salto nunca es un fallo, RFC
    técnico de 6.4.1, Decisión final 2).

    `DEPENDENCY_FAILED_OR_SKIPPED`: el step nunca se invocó porque una
    dependencia declarada en `depends_on()` falló o se saltó a su vez
    (cascada existente desde la Fase 4, ahora tipada explícitamente).

    `NOT_APPLICABLE`: el step nunca se invocó porque `applies_to()`
    devolvió `False` — la sesión actual no necesita este artefacto. Nunca
    degrada `AIPipelineRunStatus` a `partially_failed` (ver
    `AIPipelineService._is_problematic_outcome`)."""

    DEPENDENCY_FAILED_OR_SKIPPED = "dependency_failed_or_skipped"
    NOT_APPLICABLE = "not_applicable"


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
    #: Contexto longitudinal ya resuelto (Fase 6.4.1, ver
    #: `patient_context.py`) — `None` si ningún step de este *run* declaró
    #: `patient_context_requirements()` no vacío (`AIPipelineService`
    #: evita la consulta cross-sesión cuando no hace falta, ver
    #: `_union_patient_context_requirements`). Nunca lo resuelve el propio
    #: `PipelineStep`: solo lo lee, vía `applies_to(context)`.
    patient_context: LoadedPatientContext | None = None
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
    #: Plantilla realmente usada para renderizar el prompt (Fase 6.3.7) —
    #: `None` en Mock (sin `PromptTemplate` de por medio) y en pasos sin
    #: routing real. Conocido desde antes de invocar al proveedor (la
    #: plantilla ya está resuelta), así que se informa tanto en éxito como
    #: en fallo — a diferencia de `content`, que solo existe si el
    #: proveedor respondió con éxito.
    prompt_template_id: uuid.UUID | None = None
    prompt_template_version: int | None = None
    #: Solo se rellena cuando `status is None` (Fase 6.4.1) — distingue
    #: por qué se saltó sin tener que interpretar el texto libre de
    #: `skipped_reason`. `None` en `COMPLETED`/`FAILED`.
    skip_reason_code: SkipReasonCode | None = None


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

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        """Qué contexto longitudinal necesita este step — declarativo y
        puro, nunca ejecuta la consulta él mismo (Fase 6.4.1, RFC técnico
        §6). Por defecto, ninguno: preserva el comportamiento de todo
        step existente sin que cada uno tenga que sobrescribirlo. Los
        seis steps concretos heredan este cuerpo por defecto al declarar
        `PipelineStep` como clase base — ver docstring de `applies_to`."""
        return frozenset()

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        """`True` si este step debe ejecutarse en esta sesión — puro, sin
        I/O, sin repositorios, sin llamadas laterales (RFC técnico §8):
        solo puede leer `context`, ya resuelto por `AIPipelineService`
        antes de invocar al orquestador. Por defecto `True` (todo step
        aplica siempre), idéntico al comportamiento anterior a 6.4.1.

        `PipelineStep` es un `Protocol`, pero también puede usarse como
        clase base explícita: los seis `PipelineStep` concretos heredan
        de él únicamente para obtener este cuerpo por defecto y el de
        `patient_context_requirements()` sin repetirlo en cada clase — no
        se convierte en una jerarquía de clases abstractas (`depends_on`/
        `run` siguen sin cuerpo, cada clase los sobrescribe igual que
        antes). `AnamnesisStep`/`SessionNotesStep` (6.4.2+) serán los
        primeros en sobrescribir este método con lógica real."""
        return True

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
        """Lifecycle por step (RFC técnico de 6.4.1, §8):

        1. `depends_on()` contra `failed_or_skipped` — cascada existente,
           sin I/O, evaluada primero por ser la comprobación más barata.
        2. `applies_to(context)` — puro, usa `context.patient_context` ya
           resuelto por `AIPipelineService` antes de esta llamada; el
           orquestador nunca resuelve contexto ni consulta
           `patient_context_requirements()` (eso ya lo hizo el servicio
           para decidir si cargar `patient_context` en absoluto).
        3. `run()` — sin cambios.

        Un `SKIPPED_DEPENDENCY` y un `SKIPPED_NOT_APPLICABLE` bloquean
        igual a cualquier step que los declare en su `depends_on()`
        (ninguno puebla `context.outputs`) — la diferencia entre ambos es
        solo de clasificación para la agregación del *run*
        (`AIPipelineService._is_problematic_outcome`), nunca de
        propagación aguas abajo."""
        outcomes: list[PipelineStepOutcome] = []
        failed_or_skipped: set[AIArtifactType] = set()

        for step in steps:
            blocking = step.depends_on() & failed_or_skipped
            if blocking:
                outcomes.append(_dependency_skip_outcome(step.artifact_type, blocking))
                failed_or_skipped.add(step.artifact_type)
                continue

            if not step.applies_to(context):
                outcomes.append(_not_applicable_outcome(step.artifact_type))
                failed_or_skipped.add(step.artifact_type)
                continue

            outcome = await step.run(context)
            outcomes.append(outcome)
            if outcome.status == AIGenerationRunStatus.FAILED:
                failed_or_skipped.add(step.artifact_type)
            elif outcome.status == AIGenerationRunStatus.COMPLETED:
                context.outputs[step.artifact_type] = outcome.content

        return PipelineResult(outcomes=outcomes)


def _empty_outcome(
    artifact_type: AIArtifactType, *, skipped_reason: str, skip_reason_code: SkipReasonCode
) -> PipelineStepOutcome:
    """Construye el `PipelineStepOutcome` de un step nunca invocado
    (`status=None`) — compartido por los dos motivos de salto para no
    repetir los ~15 campos en blanco dos veces."""
    return PipelineStepOutcome(
        artifact_type=artifact_type,
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
        skipped_reason=skipped_reason,
        skip_reason_code=skip_reason_code,
    )


def _dependency_skip_outcome(
    artifact_type: AIArtifactType, blocking: frozenset[AIArtifactType]
) -> PipelineStepOutcome:
    blocking_names = ", ".join(sorted(t.value for t in blocking))
    return _empty_outcome(
        artifact_type,
        skipped_reason=f"Dependencia(s) no disponible(s) en esta ejecución: {blocking_names}.",
        skip_reason_code=SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED,
    )


def _not_applicable_outcome(artifact_type: AIArtifactType) -> PipelineStepOutcome:
    return _empty_outcome(
        artifact_type,
        skipped_reason="No aplica a esta sesión (applies_to() devolvió False).",
        skip_reason_code=SkipReasonCode.NOT_APPLICABLE,
    )
