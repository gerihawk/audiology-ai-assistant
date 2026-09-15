"""`extra={"context": {...}}` en los tres logs de
`app/ai_pipeline/domain/steps/base.py` (Fase 10.6, corrección de
revisión): antes pasaban campos sueltos en `extra` sin anidar bajo
`"context"`, así que `JsonFormatter` (que solo lee `record.context`, ver
app/core/logging.py) los descartaba en silencio. Mismos escenarios y
dobles que tests/test_ai_pipeline_step_base_guardrails.py — este fichero
solo verifica el logging, no el `PipelineStepOutcome` resultante."""

from __future__ import annotations

import logging
from decimal import Decimal

from app.ai_pipeline.domain.cost_budget import SessionCostBudget
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.base import run_provider_step
from app.integrations.domain.session_context import SessionContext

_TRANSCRIPT = "El paciente refiere acúfenos en el oído izquierdo."


class _FixedTokenCounter:
    def count(self, text: str, *, model: str | None = None) -> int:
        return len(text.split())


class _FixedCostEstimator:
    def __init__(self, cost_per_call: Decimal) -> None:
        self._cost_per_call = cost_per_call

    def estimate(self, *, provider, model, input_tokens, output_tokens) -> Decimal:
        return self._cost_per_call


def _context(**overrides) -> PipelineExecutionContext:
    import uuid

    defaults = dict(
        clinical_session_id=uuid.uuid4(),
        session_context=SessionContext(clinical_session_id=uuid.uuid4()),
    )
    defaults.update(overrides)
    return PipelineExecutionContext(**defaults)


def _record_for(caplog, message: str) -> logging.LogRecord:
    return next(r for r in caplog.records if r.message == message)


async def test_cost_limit_exceeded_loguea_context_con_artifact_type_y_provider(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.ai_pipeline")

    async def produce():
        return {"text": "Señal que requiere valoración profesional."}, 70, None, None, None

    budget = SessionCostBudget(limit_usd=Decimal("0.01"))
    context = _context(cost_budget=budget)

    await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("1.00")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=context,
    )

    record = _record_for(caplog, "ai_pipeline.cost_limit_exceeded")
    assert record.context == {"artifact_type": "summary", "provider_name": "mock"}


async def test_step_unexpected_error_loguea_context_con_artifact_type(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="app.ai_pipeline")

    async def boom():
        raise RuntimeError("bug interno simulado")

    await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=boom,
        context=_context(),
    )

    record = _record_for(caplog, "ai_pipeline.step_unexpected_error")
    assert record.context == {"artifact_type": "summary"}


async def test_validation_failed_loguea_context_con_los_tres_campos(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.ai_pipeline")

    async def produce():
        return {}, 70, None, None, None  # falta "text" obligatorio de SUMMARY

    await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=_context(),
    )

    record = _record_for(caplog, "ai_pipeline.validation_failed")
    assert record.context == {
        "artifact_type": "summary",
        "failure_reason": "schema_validation_failed",
        "violated_rule_count": 0,
    }
