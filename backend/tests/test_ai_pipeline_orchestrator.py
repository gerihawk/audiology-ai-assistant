"""Tests de dominio puro del orquestador del AI Pipeline — sin base de datos."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.patient_context import PatientContextRequirement
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStepOutcome,
    SequentialPipelineOrchestrator,
    SkipReasonCode,
)
from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True)
class _FakeStep:
    """Paso de prueba: siempre completa o siempre falla, según
    `should_fail`; `applies` controla `applies_to()` (Fase 6.4.1) — por
    defecto `True`, mismo comportamiento que el default real del
    `Protocol`, para no alterar los tests anteriores a 6.4.1."""

    artifact_type: AIArtifactType
    dependencies: frozenset[AIArtifactType]
    should_fail: bool = False
    calls: list[AIArtifactType] | None = None
    applies: bool = True
    requirements: frozenset[PatientContextRequirement] = frozenset()

    def depends_on(self) -> frozenset[AIArtifactType]:
        return self.dependencies

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        return self.requirements

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        return self.applies

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        if self.calls is not None:
            self.calls.append(self.artifact_type)
        now = datetime.now(UTC)
        if self.should_fail:
            return PipelineStepOutcome(
                artifact_type=self.artifact_type,
                status=AIGenerationRunStatus.FAILED,
                content=None,
                confidence=None,
                provider_name="fake",
                model_name=None,
                input_token_count=None,
                output_token_count=None,
                estimated_cost_usd=None,
                latency_ms=1,
                execution_time_ms=1,
                started_at=now,
                completed_at=now,
                failure_reason="fallo simulado",
                skipped_reason=None,
            )
        content = {"text": f"contenido de {self.artifact_type.value}"}
        return PipelineStepOutcome(
            artifact_type=self.artifact_type,
            status=AIGenerationRunStatus.COMPLETED,
            content=content,
            confidence=80,
            provider_name="fake",
            model_name="fake-v1",
            input_token_count=1,
            output_token_count=1,
            estimated_cost_usd=None,
            latency_ms=1,
            execution_time_ms=1,
            started_at=now,
            completed_at=now,
            failure_reason=None,
            skipped_reason=None,
        )


def _context() -> PipelineExecutionContext:
    session_id = uuid.uuid4()
    return PipelineExecutionContext(
        clinical_session_id=session_id, session_context=SessionContext(session_id)
    )


async def test_runs_all_steps_in_order_when_all_succeed():
    calls: list[AIArtifactType] = []
    steps = [
        _FakeStep(AIArtifactType.TRANSCRIPT, frozenset(), calls=calls),
        _FakeStep(AIArtifactType.SUMMARY, frozenset({AIArtifactType.TRANSCRIPT}), calls=calls),
        _FakeStep(
            AIArtifactType.CLINICAL_FLAGS, frozenset({AIArtifactType.TRANSCRIPT}), calls=calls
        ),
        _FakeStep(
            AIArtifactType.MISSING_INFORMATION,
            frozenset({AIArtifactType.SUMMARY, AIArtifactType.CLINICAL_FLAGS}),
            calls=calls,
        ),
        _FakeStep(
            AIArtifactType.ANAMNESIS,
            frozenset({AIArtifactType.MISSING_INFORMATION}),
            calls=calls,
        ),
    ]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    assert calls == [
        AIArtifactType.TRANSCRIPT,
        AIArtifactType.SUMMARY,
        AIArtifactType.CLINICAL_FLAGS,
        AIArtifactType.MISSING_INFORMATION,
        AIArtifactType.ANAMNESIS,
    ]
    assert all(o.status == AIGenerationRunStatus.COMPLETED for o in result.outcomes)


async def test_failed_dependency_skips_downstream_steps_without_invoking_them():
    calls: list[AIArtifactType] = []
    steps = [
        _FakeStep(AIArtifactType.TRANSCRIPT, frozenset(), should_fail=True, calls=calls),
        _FakeStep(AIArtifactType.SUMMARY, frozenset({AIArtifactType.TRANSCRIPT}), calls=calls),
        _FakeStep(
            AIArtifactType.CLINICAL_FLAGS, frozenset({AIArtifactType.TRANSCRIPT}), calls=calls
        ),
    ]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    # El paso que falló SÍ se invocó; los dependientes NUNCA se invocan.
    assert calls == [AIArtifactType.TRANSCRIPT]

    outcomes_by_type = {o.artifact_type: o for o in result.outcomes}
    assert outcomes_by_type[AIArtifactType.TRANSCRIPT].status == AIGenerationRunStatus.FAILED
    assert outcomes_by_type[AIArtifactType.TRANSCRIPT].skipped_reason is None

    assert outcomes_by_type[AIArtifactType.SUMMARY].status is None
    assert outcomes_by_type[AIArtifactType.SUMMARY].skipped_reason is not None
    assert outcomes_by_type[AIArtifactType.CLINICAL_FLAGS].status is None


async def test_independent_step_still_runs_when_sibling_fails():
    """summary y clinical_flags dependen solo de transcript, no entre sí:
    que clinical_flags falle no debe impedir que summary se ejecute."""
    calls: list[AIArtifactType] = []
    steps = [
        _FakeStep(AIArtifactType.TRANSCRIPT, frozenset(), calls=calls),
        _FakeStep(
            AIArtifactType.CLINICAL_FLAGS,
            frozenset({AIArtifactType.TRANSCRIPT}),
            should_fail=True,
            calls=calls,
        ),
        _FakeStep(AIArtifactType.SUMMARY, frozenset({AIArtifactType.TRANSCRIPT}), calls=calls),
        _FakeStep(
            AIArtifactType.MISSING_INFORMATION,
            frozenset({AIArtifactType.SUMMARY, AIArtifactType.CLINICAL_FLAGS}),
            calls=calls,
        ),
    ]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    assert AIArtifactType.SUMMARY in calls  # se ejecutó pese al fallo de su "hermano"
    assert AIArtifactType.MISSING_INFORMATION not in calls  # depende del que falló

    outcomes_by_type = {o.artifact_type: o for o in result.outcomes}
    assert outcomes_by_type[AIArtifactType.SUMMARY].status == AIGenerationRunStatus.COMPLETED
    assert outcomes_by_type[AIArtifactType.MISSING_INFORMATION].status is None


async def test_context_outputs_accumulate_only_completed_steps():
    steps = [
        _FakeStep(AIArtifactType.TRANSCRIPT, frozenset()),
        _FakeStep(AIArtifactType.SUMMARY, frozenset({AIArtifactType.TRANSCRIPT})),
    ]
    context = _context()

    await SequentialPipelineOrchestrator().run(context, steps)

    assert AIArtifactType.TRANSCRIPT in context.outputs
    assert AIArtifactType.SUMMARY in context.outputs
    assert context.outputs[AIArtifactType.TRANSCRIPT] == {"text": "contenido de transcript"}


# --- Fase 6.4.1: applies_to()/NOT_APPLICABLE ---------------------------------


async def test_default_applies_to_is_true_for_step_without_override():
    """Un step que no declara `applies` (default `True` de `_FakeStep`,
    espejo del default real de `PipelineStep`) se comporta exactamente
    como antes de 6.4.1: siempre se invoca."""
    calls: list[AIArtifactType] = []
    steps = [_FakeStep(AIArtifactType.TRANSCRIPT, frozenset(), calls=calls)]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    assert calls == [AIArtifactType.TRANSCRIPT]
    assert result.outcomes[0].status == AIGenerationRunStatus.COMPLETED


async def test_applies_to_false_produces_skipped_not_applicable_without_invoking_run():
    calls: list[AIArtifactType] = []
    steps = [_FakeStep(AIArtifactType.ANAMNESIS, frozenset(), applies=False, calls=calls)]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    assert calls == []  # run() nunca se invocó
    outcome = result.outcomes[0]
    assert outcome.status is None
    assert outcome.skip_reason_code == SkipReasonCode.NOT_APPLICABLE
    assert outcome.failure_reason is None  # NOT_APPLICABLE nunca es un fallo
    assert outcome.skipped_reason is not None


async def test_not_applicable_output_is_not_published_to_context_outputs():
    steps = [_FakeStep(AIArtifactType.ANAMNESIS, frozenset(), applies=False)]
    context = _context()

    await SequentialPipelineOrchestrator().run(context, steps)

    assert AIArtifactType.ANAMNESIS not in context.outputs


async def test_not_applicable_step_blocks_downstream_hard_dependency():
    """Un dependiente declarado en `depends_on()` de un step NOT_APPLICABLE
    se salta con SKIPPED_DEPENDENCY — la ausencia de output bloquea igual
    que un FAILED, aunque no sea un fallo (RFC técnico §10)."""
    calls: list[AIArtifactType] = []
    steps = [
        _FakeStep(AIArtifactType.ANAMNESIS, frozenset(), applies=False, calls=calls),
        _FakeStep(
            AIArtifactType.SUMMARY, frozenset({AIArtifactType.ANAMNESIS}), calls=calls
        ),  # dependencia artificial solo para probar la propagación
    ]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    assert calls == []  # ni el NOT_APPLICABLE ni su dependiente invocan run()
    outcomes_by_type = {o.artifact_type: o for o in result.outcomes}
    assert outcomes_by_type[AIArtifactType.ANAMNESIS].skip_reason_code == (
        SkipReasonCode.NOT_APPLICABLE
    )
    downstream = outcomes_by_type[AIArtifactType.SUMMARY]
    assert downstream.status is None
    assert downstream.skip_reason_code == SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED


async def test_dependency_cascade_skip_still_reports_dependency_skip_reason_code():
    """Regresión explícita: la cascada de fallo existente sigue marcando
    `DEPENDENCY_FAILED_OR_SKIPPED`, nunca `NOT_APPLICABLE`."""
    steps = [
        _FakeStep(AIArtifactType.TRANSCRIPT, frozenset(), should_fail=True),
        _FakeStep(AIArtifactType.SUMMARY, frozenset({AIArtifactType.TRANSCRIPT})),
    ]

    result = await SequentialPipelineOrchestrator().run(_context(), steps)

    outcomes_by_type = {o.artifact_type: o for o in result.outcomes}
    assert outcomes_by_type[AIArtifactType.SUMMARY].skip_reason_code == (
        SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED
    )
