"""Tests de cableado de guardarraíles en `run_provider_step`
(app/ai_pipeline/domain/steps/base.py) — sin BD, sin proveedor real. Ver
docs/fase-6-rfc.md §5.1/§5.5/§6.3 y §17 del encargo de la Fase 6.1
(transaccionalidad: ningún fallo de guardarraíl puede devolver
`COMPLETED`)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.ai_pipeline.domain.cost_budget import SessionCostBudget
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.retry_policy import RetryConfig
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
    defaults = dict(
        clinical_session_id=uuid.uuid4(),
        session_context=SessionContext(clinical_session_id=uuid.uuid4()),
    )
    defaults.update(overrides)
    return PipelineExecutionContext(**defaults)


async def _produce_valid_summary():
    return {"text": "Señal que requiere valoración profesional."}, 70


# --- persistence boundary: ningún fallo llega a COMPLETED -----------------


async def test_contenido_inseguro_nunca_se_marca_completado():
    async def produce():
        return {"text": "El paciente tiene una posible pérdida auditiva."}, 70

    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=_context(),
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == AIGenerationFailureReason.SAFETY_POLICY_FAILED.value
    assert outcome.content is None


async def test_schema_invalido_nunca_se_marca_completado():
    async def produce():
        return {}, 70  # falta "text" obligatorio de SUMMARY

    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=_context(),
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED.value


async def test_contenido_valido_se_marca_completado_con_source_map():
    async def produce():
        return {
            "flags": [
                {
                    "category": "tinnitus_unilateral",
                    "description": "Posible motivo de derivación.",
                    "source_excerpt": "acúfenos en el oído izquierdo",
                    "ruleset_name": "demo_generic_v1",
                }
            ]
        }, 65

    outcome = await run_provider_step(
        artifact_type=AIArtifactType.CLINICAL_FLAGS,
        provider_name="mock",
        model_name=None,
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=_context(),
    )
    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert outcome.source_map is not None
    assert "flags[0]" in outcome.source_map


# --- límite de coste: pre-flight, el proveedor no se invoca ----------------


async def test_coste_potencial_excede_el_limite_no_invoca_al_proveedor():
    calls = 0

    async def produce():
        nonlocal calls
        calls += 1
        return await _produce_valid_summary()

    budget = SessionCostBudget(limit_usd=Decimal("0.01"))
    context = _context(cost_budget=budget)

    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("1.00")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == AIGenerationFailureReason.COST_LIMIT_EXCEEDED.value
    assert calls == 0
    assert budget.accumulated_usd == Decimal("0")  # nunca se registra un coste no incurrido


async def test_coste_dentro_del_limite_se_acumula_tras_completar():
    budget = SessionCostBudget(limit_usd=Decimal("10.00"))
    context = _context(cost_budget=budget)

    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0.05")),
        input_text=_TRANSCRIPT,
        produce=_produce_valid_summary,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert budget.accumulated_usd == Decimal("0.05")


async def test_limite_desactivado_por_defecto_nunca_bloquea():
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("999")),
        input_text=_TRANSCRIPT,
        produce=_produce_valid_summary,
        context=_context(),  # cost_budget=None por defecto
    )
    assert outcome.status == AIGenerationRunStatus.COMPLETED


# --- reintentos: acotados, y cuentan contra el mismo presupuesto -----------


async def test_fallo_transitorio_se_reintenta_hasta_el_maximo_general():
    attempts = 0

    async def flaky_produce():
        nonlocal attempts
        attempts += 1
        raise TransientProviderError("simulado", reason=AIGenerationFailureReason.PROVIDER_TIMEOUT)

    context = _context(retry_config=RetryConfig(max_general_retries=2, backoff_base_seconds=0))
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=flaky_produce,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == AIGenerationFailureReason.PROVIDER_TIMEOUT.value
    assert attempts == 3  # intento inicial + 2 reintentos


async def test_fallo_transitorio_se_recupera_si_un_reintento_tiene_exito():
    attempts = 0

    async def flaky_then_ok():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise TransientProviderError(reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE)
        return await _produce_valid_summary()

    context = _context(retry_config=RetryConfig(max_general_retries=2, backoff_base_seconds=0))
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=flaky_then_ok,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert attempts == 2


async def test_fallo_de_seguridad_se_reintenta_como_mucho_una_vez():
    attempts = 0

    async def always_unsafe():
        nonlocal attempts
        attempts += 1
        return {"text": "diagnóstico confirmado"}, 70

    context = _context(
        retry_config=RetryConfig(
            max_general_retries=2, max_regenerative_retries=1, backoff_base_seconds=0
        )
    )
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=always_unsafe,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert attempts == 2  # intento inicial + 1 reintento regenerativo (no 3)


async def test_limite_de_coste_nunca_se_reintenta():
    calls = 0

    async def produce():
        nonlocal calls
        calls += 1
        return await _produce_valid_summary()

    budget = SessionCostBudget(limit_usd=Decimal("0.01"))
    context = _context(
        cost_budget=budget, retry_config=RetryConfig(max_general_retries=2, backoff_base_seconds=0)
    )
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("1.00")),
        input_text=_TRANSCRIPT,
        produce=produce,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert calls == 0


async def test_error_inesperado_no_es_retryable():
    attempts = 0

    async def boom():
        nonlocal attempts
        attempts += 1
        raise RuntimeError("bug interno simulado")

    context = _context(retry_config=RetryConfig(max_general_retries=2, backoff_base_seconds=0))
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=boom,
        context=context,
    )
    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == AIGenerationFailureReason.UNEXPECTED_INTERNAL_ERROR.value
    assert attempts == 1


async def test_sin_context_se_comporta_como_guardarrailes_desactivados():
    outcome = await run_provider_step(
        artifact_type=AIArtifactType.SUMMARY,
        provider_name="mock",
        model_name="mock-v1",
        token_counter=_FixedTokenCounter(),
        cost_estimator=_FixedCostEstimator(Decimal("0")),
        input_text=_TRANSCRIPT,
        produce=_produce_valid_summary,
        context=None,
    )
    assert outcome.status == AIGenerationRunStatus.COMPLETED
