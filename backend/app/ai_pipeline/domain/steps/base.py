"""Ejecución uniforme de un paso del pipeline: cronometraje, tokens, coste
y traducción de cualquier fallo del proveedor en un `PipelineStepOutcome`
`FAILED` — nunca propaga la excepción del proveedor hacia el orquestador.
Compartido por los cinco `PipelineStep` concretos para no repetir el mismo
try/except cinco veces.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.pipeline import PipelineStepOutcome
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.token_counter import TokenCounter


async def run_provider_step(
    *,
    artifact_type: AIArtifactType,
    provider_name: str,
    model_name: str | None,
    token_counter: TokenCounter,
    cost_estimator: CostEstimator,
    input_text: str,
    produce: Callable[[], Awaitable[tuple[dict[str, Any], int]]],
) -> PipelineStepOutcome:
    """`produce()` invoca al proveedor y devuelve `(content, confidence)`.

    En este MVP, sin overhead adicional medible por separado de la
    llamada al proveedor, `latency_ms` y `execution_time_ms` coinciden —
    ver docs/ai-pipeline-architecture.md §7.6.
    """
    started_at = datetime.now(UTC)
    perf_start = time.perf_counter()
    try:
        content, confidence = await produce()
    except Exception as exc:  # noqa: BLE001 — límite del proveedor: cualquier
        # fallo (del mock hoy, de un SDK real mañana) se traduce en un
        # AIGenerationRun `failed`, nunca propaga hasta el orquestador.
        elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
        return PipelineStepOutcome(
            artifact_type=artifact_type,
            status=AIGenerationRunStatus.FAILED,
            content=None,
            confidence=None,
            provider_name=provider_name,
            model_name=model_name,
            input_token_count=token_counter.count(input_text) if input_text else None,
            output_token_count=None,
            estimated_cost_usd=None,
            latency_ms=elapsed_ms,
            execution_time_ms=elapsed_ms,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            failure_reason=str(exc) or exc.__class__.__name__,
            skipped_reason=None,
        )

    elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
    input_tokens = token_counter.count(input_text) if input_text else 0
    output_tokens = token_counter.count(_content_as_text(content))
    cost = cost_estimator.estimate(
        provider=provider_name,
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return PipelineStepOutcome(
        artifact_type=artifact_type,
        status=AIGenerationRunStatus.COMPLETED,
        content=content,
        confidence=confidence,
        provider_name=provider_name,
        model_name=model_name,
        input_token_count=input_tokens,
        output_token_count=output_tokens,
        estimated_cost_usd=cost,
        latency_ms=elapsed_ms,
        execution_time_ms=elapsed_ms,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        failure_reason=None,
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
