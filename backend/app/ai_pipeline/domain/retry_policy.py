"""Política de reintentos acotados — ver docs/fase-6-rfc.md §5.5 y el
encargo de la Fase 6.1, punto 8. Solo la infraestructura de clasificación
y backoff: `steps/base.py` es quien ejecuta el bucle acotado. Sin
proveedor real todavía, ningún `Mock*Generator` agota nunca sus
reintentos en producción — la mecánica se demuestra con dobles de test.

Dos grupos, según §5.5:

- `_GENERAL_RETRYABLE`: timeout/rate-limit/indisponibilidad transitoria,
  formato inválido, schema y respuesta evasiva — hasta
  `Settings.ai_pipeline_max_general_retries` (2 por defecto, 3 intentos
  totales).
- `_REGENERATIVE_RETRYABLE`: grounding y seguridad — como mucho
  `Settings.ai_pipeline_max_regenerative_retries` (1 por defecto) con
  instrucciones reforzadas; si se repite, el step falla.

`cost_limit_exceeded` y `unexpected_internal_error` nunca son
retryable — 0 reintentos.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.ai_pipeline.domain.errors import AIGenerationFailureReason


@dataclass(slots=True, frozen=True)
class RetryConfig:
    """Resuelta una vez por `AIPipelineService` desde `Settings` y
    compartida vía `PipelineExecutionContext` — nunca leída directamente
    de `Settings` dentro del dominio (ver app/core/config.py)."""

    max_general_retries: int = 2
    max_regenerative_retries: int = 1
    backoff_base_seconds: float = 0.0


_GENERAL_RETRYABLE = frozenset(
    {
        AIGenerationFailureReason.PROVIDER_TIMEOUT,
        AIGenerationFailureReason.PROVIDER_RATE_LIMITED,
        AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
        AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED,
        AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE,
    }
)
_REGENERATIVE_RETRYABLE = frozenset(
    {
        AIGenerationFailureReason.GROUNDING_FAILED,
        AIGenerationFailureReason.SAFETY_POLICY_FAILED,
    }
)


def max_retries_for(
    reason: AIGenerationFailureReason, *, max_general: int, max_regenerative: int
) -> int:
    if reason in _GENERAL_RETRYABLE:
        return max_general
    if reason in _REGENERATIVE_RETRYABLE:
        return max_regenerative
    return 0


def backoff_seconds(attempt: int, *, base_seconds: float) -> float:
    """`attempt` empieza en 0 para el primer reintento. `base_seconds<=0`
    (valor por defecto de `Settings` en development/test) desactiva la
    espera real sin cambiar la decisión de si se reintenta."""
    if base_seconds <= 0:
        return 0.0
    return base_seconds * (2**attempt) + random.uniform(0, base_seconds)
