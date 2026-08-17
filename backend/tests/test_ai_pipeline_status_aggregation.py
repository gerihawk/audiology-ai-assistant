"""Tests de dominio puro de la agregación de `AIPipelineRunStatus` — Fase
6.4.1, Decisión final 2 del RFC técnico: `SKIPPED_NOT_APPLICABLE` nunca
degrada el resultado del *run*; `SKIPPED_DEPENDENCY` sí conserva la
semántica de problema ya existente desde la Fase 4."""

from __future__ import annotations

from datetime import UTC, datetime

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.pipeline import PipelineStepOutcome, SkipReasonCode
from app.ai_pipeline.service import _is_problematic_outcome, _resolve_pipeline_status


def _completed_outcome(artifact_type: AIArtifactType) -> PipelineStepOutcome:
    now = datetime.now(UTC)
    return PipelineStepOutcome(
        artifact_type=artifact_type,
        status=AIGenerationRunStatus.COMPLETED,
        content={"text": "ok"},
        confidence=80,
        provider_name="mock",
        model_name="mock-v1",
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


def _failed_outcome(artifact_type: AIArtifactType) -> PipelineStepOutcome:
    now = datetime.now(UTC)
    return PipelineStepOutcome(
        artifact_type=artifact_type,
        status=AIGenerationRunStatus.FAILED,
        content=None,
        confidence=None,
        provider_name="mock",
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


def _skip_outcome(
    artifact_type: AIArtifactType, reason_code: SkipReasonCode
) -> PipelineStepOutcome:
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
        skipped_reason="motivo de prueba",
        skip_reason_code=reason_code,
    )


class TestIsProblematicOutcome:
    def test_not_applicable_skip_is_not_problematic(self):
        outcome = _skip_outcome(AIArtifactType.ANAMNESIS, SkipReasonCode.NOT_APPLICABLE)
        assert _is_problematic_outcome(outcome) is False

    def test_dependency_skip_is_problematic(self):
        outcome = _skip_outcome(AIArtifactType.SUMMARY, SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED)
        assert _is_problematic_outcome(outcome) is True


class TestResolvePipelineStatusWithSkipClassification:
    """Reproduce, campo a campo, los casos mínimos del RFC técnico §11:
    la clasificación problematic/non-problematic ocurre ANTES de llamar
    a `_resolve_pipeline_status` (en el bucle de `_execute_pipeline_run`);
    aquí se verifica que, una vez clasificados, los dos booleanos
    resultantes producen el `AIPipelineRunStatus` correcto — mismo
    contrato que ya tenía `_resolve_pipeline_status` antes de 6.4.1."""

    def test_all_completed_is_completed(self):
        outcomes = [_completed_outcome(AIArtifactType.TRANSCRIPT)]
        any_completed, any_failed_or_skipped = _aggregate(outcomes)
        assert _resolve_pipeline_status(any_completed, any_failed_or_skipped) == "completed"

    def test_not_applicable_plus_completed_is_completed(self):
        outcomes = [
            _completed_outcome(AIArtifactType.TRANSCRIPT),
            _skip_outcome(AIArtifactType.ANAMNESIS, SkipReasonCode.NOT_APPLICABLE),
        ]
        any_completed, any_failed_or_skipped = _aggregate(outcomes)
        assert _resolve_pipeline_status(any_completed, any_failed_or_skipped) == "completed"

    def test_failed_step_is_partially_failed_when_something_else_completed(self):
        outcomes = [
            _completed_outcome(AIArtifactType.TRANSCRIPT),
            _failed_outcome(AIArtifactType.SUMMARY),
        ]
        any_completed, any_failed_or_skipped = _aggregate(outcomes)
        assert _resolve_pipeline_status(any_completed, any_failed_or_skipped) == "partially_failed"

    def test_dependency_skip_derived_from_failure_is_partially_failed(self):
        outcomes = [
            _completed_outcome(AIArtifactType.TRANSCRIPT),
            _failed_outcome(AIArtifactType.SUMMARY),
            _skip_outcome(
                AIArtifactType.MISSING_INFORMATION, SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED
            ),
        ]
        any_completed, any_failed_or_skipped = _aggregate(outcomes)
        assert _resolve_pipeline_status(any_completed, any_failed_or_skipped) == "partially_failed"


def _aggregate(outcomes: list[PipelineStepOutcome]) -> tuple[bool, bool]:
    """Reproduce el bucle real de `_execute_pipeline_run` (sin BD) para
    calcular `(any_completed, any_failed_or_skipped)` a partir de una
    lista de outcomes ya construidos."""
    any_completed = False
    any_failed_or_skipped = False
    for outcome in outcomes:
        if outcome.status is None:
            if _is_problematic_outcome(outcome):
                any_failed_or_skipped = True
            continue
        if outcome.status == AIGenerationRunStatus.FAILED:
            any_failed_or_skipped = True
            continue
        any_completed = True
    return any_completed, any_failed_or_skipped
