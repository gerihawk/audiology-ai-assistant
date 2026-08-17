"""AnamnesisUpdateStep — Hito 6.5.3, RFC técnico de 6.5 §3.

Operación EXPLÍCITA: deliberadamente ausente de `PIPELINE_STEP_ORDER` — no
la ejecuta `SequentialPipelineOrchestrator`, no la disparan `run-pipeline`
ni `run-mock-pipeline`. La sesión que la dispara resuelve su propio
`PipelineExecutionContext` (transcript de la sesión actual ya en
`context.outputs[TRANSCRIPT]`, baseline aprobado ya en
`context.patient_context.previous_approved_anamnesis`) y llama a
`applies_to()`/`run()` directamente — ver
`AIPipelineService.propose_anamnesis_update`. `depends_on()` devuelve un
conjunto vacío: ningún orquestador automático evalúa jamás este step
contra el grafo de `PIPELINE_STEP_ORDER`, así que declarar una dependencia
ahí no tendría ningún efecto real.

Secuencia de `run()` (RFC técnico de 6.5 §3 del encargo de 6.5.3, deliberadamente
distinta de `run_provider_step`/`validate_generated_content`): generar →
`validate_update_batch()` (reglas de transición) → `verify_update_grounding()`
(grounding ACOTADO, solo campos modificados, nunca el documento completo) →
`materialize_anamnesis()` (aplica el diff + valida el esquema cerrado
completo). Nunca persiste — produce un `PipelineStepOutcome` listo para que
el servicio decida (ver `AIPipelineService.propose_anamnesis_update`, que
además decide no persistir nada si `content` resulta idéntico al baseline,
es decir, cero campos cambiados)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from app.ai_pipeline.domain.anamnesis_update import (
    InvalidAnamnesisUpdateError,
    materialize_anamnesis,
    validate_update_batch,
    verify_update_grounding,
)
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.patient_context import PatientContextRequirement
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.integrations.domain.anamnesis_update_generator import AnamnesisUpdateGenerator

_CONFIDENCE = 55


class AnamnesisUpdateStep(PipelineStep):
    artifact_type = AIArtifactType.ANAMNESIS

    def __init__(
        self,
        generator: AnamnesisUpdateGenerator,
        *,
        provider_name: str = "mock",
        model_name: str | None = "mock-v1",
    ) -> None:
        self._generator = generator
        self._provider_name = provider_name
        self._model_name = model_name

    def depends_on(self) -> frozenset[AIArtifactType]:
        return frozenset()

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        return frozenset({PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS})

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        """`True` únicamente si existe baseline (anamnesis previa aprobada
        de otra sesión) — sin baseline, "proponer una actualización" no
        tiene sentido semántico. Puro, sin I/O: solo lee
        `context.patient_context`, ya resuelto por el servicio."""
        return (
            context.patient_context is not None
            and context.patient_context.previous_approved_anamnesis is not None
        )

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        assert context.patient_context is not None  # invariante: applies_to() ya lo garantizó
        previous_ref = context.patient_context.previous_approved_anamnesis
        assert previous_ref is not None  # ídem

        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]

        started_at = datetime.now(UTC)
        perf_start = time.perf_counter()

        result = await self._generator.generate(
            transcript_text, previous_ref.content, context=context.session_context
        )

        try:
            validate_update_batch(result.updates)
        except InvalidAnamnesisUpdateError:
            return self._failed_outcome(
                started_at, perf_start, AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED
            )

        # Grounding ACOTADO: exclusivamente los campos que `result.updates`
        # propone cambiar, contra el transcript de la sesión ACTUAL — nunca
        # `validate_generated_content()`/`_build_source_map()`, que
        # revalidarían también los campos carried-forward del baseline
        # contra un transcript al que no pertenecen (auditoría de 6.5, §9/§19).
        grounding = verify_update_grounding(result.updates, transcript_text)
        if not grounding.ok:
            return self._failed_outcome(
                started_at, perf_start, AIGenerationFailureReason.GROUNDING_FAILED
            )

        try:
            materialized = materialize_anamnesis(previous_ref.content, result.updates)
        except InvalidAnamnesisUpdateError:
            return self._failed_outcome(
                started_at, perf_start, AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED
            )

        elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
        return PipelineStepOutcome(
            artifact_type=self.artifact_type,
            status=AIGenerationRunStatus.COMPLETED,
            content=materialized,
            confidence=_CONFIDENCE,
            provider_name=self._provider_name,
            model_name=self._model_name,
            input_token_count=result.input_tokens,
            output_token_count=result.output_tokens,
            estimated_cost_usd=None,
            latency_ms=elapsed_ms,
            execution_time_ms=elapsed_ms,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            failure_reason=None,
            skipped_reason=None,
            source_map=grounding.source_map,
        )

    def _failed_outcome(
        self, started_at: datetime, perf_start: float, reason: AIGenerationFailureReason
    ) -> PipelineStepOutcome:
        elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
        return PipelineStepOutcome(
            artifact_type=self.artifact_type,
            status=AIGenerationRunStatus.FAILED,
            content=None,
            confidence=None,
            provider_name=self._provider_name,
            model_name=self._model_name,
            input_token_count=None,
            output_token_count=None,
            estimated_cost_usd=None,
            latency_ms=elapsed_ms,
            execution_time_ms=elapsed_ms,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            failure_reason=reason.value,
            skipped_reason=None,
        )
