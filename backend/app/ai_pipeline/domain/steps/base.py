"""Ejecución uniforme de un paso del pipeline: cronometraje, tokens, coste
y traducción de cualquier fallo (del proveedor o de los guardarraíles de
runtime) en un `PipelineStepOutcome` `FAILED` con un motivo tipado —
nunca propaga la excepción del proveedor hacia el orquestador. Compartido
por los cinco `PipelineStep` concretos para no repetir el mismo
try/except cinco veces.

Fase 6.1 (docs/fase-6-rfc.md §5.1/§5.5/§6.3): este es el chokepoint único
por el que TODO step LLM pasa antes de poder devolver `COMPLETED` —
"ningún step pueda omitirlo" (§5.2). Secuencia por intento:

1. presupuesto de coste (§6.3): estimación "peor caso razonable" con el
   `input_text` ya conocido y `max_output_tokens_estimate` como techo de
   salida; si superaría el límite, el proveedor NO se invoca y el step
   falla con `cost_limit_exceeded` — nunca retryable.
2. `produce()` — invoca al proveedor (Mock hoy).
3. `validate_generated_content()` (`validation_pipeline.py`) — schema →
   evasiva → grounding/source_map → safety, en ese orden (§5.1).
4. si todo pasa: coste real acumulado en `cost_budget`, `COMPLETED`.
5. si algo falla: reintento acotado según `retry_policy.py` (los
   reintentos cuentan contra el mismo `cost_budget`, §6.3) o `FAILED`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.pipeline import (
    DEFAULT_MAX_OUTPUT_TOKENS_ESTIMATE,
    PipelineExecutionContext,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.retry_policy import RetryConfig, backoff_seconds, max_retries_for
from app.ai_pipeline.domain.validation_pipeline import validate_generated_content
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.token_counter import TokenCounter

logger = logging.getLogger("app.ai_pipeline")


#: `produce()` devuelve
#: `(content, confidence, input_tokens, output_tokens, reasoning_tokens)`
#: — los tres últimos son el usage REAL reportado por el proveedor (Fase
#: 6.3, `LanguageModelResponse.input_tokens`/`output_tokens`/
#: `reasoning_tokens`), `None` si el proveedor no lo reporta (Mock hoy,
#: Anthropic/OpenAI hoy para `reasoning_tokens` — solo Google lo expone
#: como contador aditivo separado, ver ese dataclass). Nunca se sustituye
#: un usage real por la estimación heurística de `TokenCounter` — ver
#: `_attempt()`. `reasoning_tokens`, cuando existe, se suma a
#: `output_tokens` únicamente para estimar coste y para lo que se
#: persiste como `output_token_count` — nunca redefine el significado de
#: `output_tokens` en `LanguageModelResponse`/los `*Draft`.
ProduceResult = tuple[dict[str, Any], int, int | None, int | None, int | None]


async def run_provider_step(
    *,
    artifact_type: AIArtifactType,
    provider_name: str,
    model_name: str | None,
    token_counter: TokenCounter,
    cost_estimator: CostEstimator,
    input_text: str,
    produce: Callable[[], Awaitable[ProduceResult]],
    context: PipelineExecutionContext | None = None,
) -> PipelineStepOutcome:
    """`produce()` invoca al proveedor y devuelve `(content, confidence)`.

    `context`, si se recibe, aporta `cost_budget`/`retry_config`/
    `max_output_tokens_estimate` (Fase 6.1) — `None` en cada uno equivale
    a "guardarraíl desactivado", mismo comportamiento que antes del hito
    6.1 (usado así hoy por `Mock Pipeline`, sin proveedor real).

    En este MVP, sin overhead adicional medible por separado de la
    llamada al proveedor, `latency_ms` y `execution_time_ms` coinciden —
    ver docs/ai-pipeline-architecture.md §7.6 (por intento, no acumulado
    entre reintentos).
    """
    cost_budget = context.cost_budget if context is not None else None
    retry_config = context.retry_config if context is not None else RetryConfig()
    max_output_tokens_estimate = (
        context.max_output_tokens_estimate
        if context is not None
        else DEFAULT_MAX_OUTPUT_TOKENS_ESTIMATE
    )
    input_tokens = token_counter.count(input_text) if input_text else 0

    attempt = 0
    while True:
        started_at = datetime.now(UTC)
        perf_start = time.perf_counter()

        if cost_budget is not None:
            worst_case_cost = cost_estimator.estimate(
                provider=provider_name,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=max_output_tokens_estimate,
            )
            if cost_budget.would_exceed(worst_case_cost):
                logger.warning(
                    "ai_pipeline.cost_limit_exceeded",
                    extra={"artifact_type": artifact_type.value, "provider_name": provider_name},
                )
                return _failed_outcome(
                    artifact_type=artifact_type,
                    provider_name=provider_name,
                    model_name=model_name,
                    input_tokens=input_tokens,
                    started_at=started_at,
                    perf_start=perf_start,
                    failure_reason=AIGenerationFailureReason.COST_LIMIT_EXCEEDED,
                )

        outcome = await _attempt(
            artifact_type=artifact_type,
            provider_name=provider_name,
            model_name=model_name,
            token_counter=token_counter,
            cost_estimator=cost_estimator,
            input_text=input_text,
            input_tokens=input_tokens,
            produce=produce,
            cost_budget=cost_budget,
            started_at=started_at,
            perf_start=perf_start,
        )
        if outcome.status == AIGenerationRunStatus.COMPLETED:
            return outcome

        assert outcome.failure_reason is not None  # invariante: FAILED siempre trae motivo tipado
        reason = AIGenerationFailureReason(outcome.failure_reason)
        max_retries = max_retries_for(
            reason,
            max_general=retry_config.max_general_retries,
            max_regenerative=retry_config.max_regenerative_retries,
        )
        if attempt >= max_retries:
            return outcome

        delay = backoff_seconds(attempt, base_seconds=retry_config.backoff_base_seconds)
        await asyncio.sleep(delay)
        attempt += 1


async def _attempt(
    *,
    artifact_type: AIArtifactType,
    provider_name: str,
    model_name: str | None,
    token_counter: TokenCounter,
    cost_estimator: CostEstimator,
    input_text: str,
    input_tokens: int,
    produce: Callable[[], Awaitable[ProduceResult]],
    cost_budget: Any,
    started_at: datetime,
    perf_start: float,
) -> PipelineStepOutcome:
    try:
        (
            content,
            confidence,
            reported_input_tokens,
            reported_output_tokens,
            reported_reasoning_tokens,
        ) = await produce()
    except TransientProviderError as exc:
        return _failed_outcome(
            artifact_type=artifact_type,
            provider_name=provider_name,
            model_name=model_name,
            input_tokens=input_tokens,
            started_at=started_at,
            perf_start=perf_start,
            failure_reason=exc.reason,
        )
    except Exception:  # noqa: BLE001 — límite del proveedor: cualquier fallo
        # inesperado (del mock hoy, de un SDK real mañana) se traduce en un
        # AIGenerationRun `failed` tipado, nunca propaga hasta el orquestador.
        logger.exception(
            "ai_pipeline.step_unexpected_error", extra={"artifact_type": artifact_type.value}
        )
        return _failed_outcome(
            artifact_type=artifact_type,
            provider_name=provider_name,
            model_name=model_name,
            input_tokens=input_tokens,
            started_at=started_at,
            perf_start=perf_start,
            failure_reason=AIGenerationFailureReason.UNEXPECTED_INTERNAL_ERROR,
        )

    # Usage real reportado por el proveedor si existe, nunca sustituido por
    # la estimación heurística de `TokenCounter` — ver docstring de
    # `ProduceResult`. `input_tokens` (heurístico) ya se calculó antes de
    # invocar `produce()`, para el presupuesto de coste previo a la llamada.
    final_input_tokens = (
        reported_input_tokens if reported_input_tokens is not None else input_tokens
    )

    validation = validate_generated_content(artifact_type, content, input_text)
    if not validation.ok:
        assert validation.failure_reason is not None  # invariante: ok=False siempre trae motivo
        logger.info(
            "ai_pipeline.validation_failed",
            extra={
                "artifact_type": artifact_type.value,
                "failure_reason": validation.failure_reason.value,
                "violated_rule_count": len(validation.violated_rule_ids),
            },
        )
        return _failed_outcome(
            artifact_type=artifact_type,
            provider_name=provider_name,
            model_name=model_name,
            input_tokens=final_input_tokens,
            started_at=started_at,
            perf_start=perf_start,
            failure_reason=validation.failure_reason,
        )

    elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
    final_output_tokens = (
        reported_output_tokens
        if reported_output_tokens is not None
        else token_counter.count(_content_as_text(validation.content))
    )
    # Tokens de razonamiento facturables (Google Gemini, ver docstring de
    # `LanguageModelResponse.reasoning_tokens`) — se suman SOLO aquí, para
    # coste y para lo que se persiste como `output_token_count`. Si no hay
    # usage real reportado (`reported_output_tokens is None`, se cayó a la
    # heurística), tampoco puede haber `reasoning_tokens` real que sumar —
    # invariante que cada provider ya respeta al construir su
    # `LanguageModelResponse`, reforzado aquí por si acaso.
    billable_output_tokens = final_output_tokens + (
        (reported_reasoning_tokens or 0) if reported_output_tokens is not None else 0
    )
    cost = cost_estimator.estimate(
        provider=provider_name,
        model=model_name,
        input_tokens=final_input_tokens,
        output_tokens=billable_output_tokens,
    )
    if cost_budget is not None:
        cost_budget.record(cost)

    return PipelineStepOutcome(
        artifact_type=artifact_type,
        status=AIGenerationRunStatus.COMPLETED,
        content=validation.content,
        confidence=confidence,
        provider_name=provider_name,
        model_name=model_name,
        input_token_count=final_input_tokens,
        output_token_count=billable_output_tokens,
        estimated_cost_usd=cost,
        latency_ms=elapsed_ms,
        execution_time_ms=elapsed_ms,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        failure_reason=None,
        skipped_reason=None,
        source_map=validation.source_map,
    )


def _failed_outcome(
    *,
    artifact_type: AIArtifactType,
    provider_name: str,
    model_name: str | None,
    input_tokens: int,
    started_at: datetime,
    perf_start: float,
    failure_reason: AIGenerationFailureReason,
) -> PipelineStepOutcome:
    elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
    return PipelineStepOutcome(
        artifact_type=artifact_type,
        status=AIGenerationRunStatus.FAILED,
        content=None,
        confidence=None,
        provider_name=provider_name,
        model_name=model_name,
        input_token_count=input_tokens,
        output_token_count=None,
        estimated_cost_usd=None,
        latency_ms=elapsed_ms,
        execution_time_ms=elapsed_ms,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        failure_reason=failure_reason.value,
        skipped_reason=None,
    )


def _content_as_text(content: dict[str, Any]) -> str:
    """Aproximación simple para `TokenCounter`: concatena el texto real del
    contenido generado. No pretende ser un serializador fiel.

    Extrae recursivamente los valores string de listas/diccionarios
    anidados (p. ej. `segments` en `transcript` desde la Fase 5, o `flags`
    en `clinical_flags`) en vez de convertir la estructura entera con
    `str(value)` — eso inflaba el recuento con sintaxis de Python
    (`{`, `'speaker':`, claves...) además del propio texto, detectado con
    una llamada real a AssemblyAI (ver docs/transcription-benchmark.md):
    con `segments` presente, `output_token_count` llegó a duplicarse.
    Los escalares no-string (`duration_ms`, `None`, booleanos) se
    convierten con `str()` igual que antes."""
    return " ".join(part for part in (_extract_text(value) for value in content.values()) if part)


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(part for part in (_extract_text(v) for v in value.values()) if part)
    if isinstance(value, list):
        return " ".join(part for part in (_extract_text(v) for v in value) if part)
    return str(value)
