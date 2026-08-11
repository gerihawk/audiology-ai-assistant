"""Motivos de fallo tipados de una ejecución de step y excepción de
proveedor transitoria — ver docs/fase-6-rfc.md §5.5.

`AIGenerationRun.failure_reason`/`PipelineStepOutcome.failure_reason`
pasan a ser siempre uno de estos valores (nunca texto libre de una
excepción): permite que la API/UI futura distinga "proveedor
temporalmente no disponible" de "salida inválida" de "evidencia
insuficiente" de "bloqueado por seguridad" de "límite de coste", sin
mostrar detalles sensibles ni convertirlos todos en un fallo opaco (ver
§5.5 y el encargo de la Fase 6.1, punto 7).
"""

from __future__ import annotations

from enum import StrEnum


class AIGenerationFailureReason(StrEnum):
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_RESPONSE_FORMAT = "invalid_response_format"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    EVASIVE_OR_META_RESPONSE = "evasive_or_meta_response"
    GROUNDING_FAILED = "grounding_failed"
    SAFETY_POLICY_FAILED = "safety_policy_failed"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    UNEXPECTED_INTERNAL_ERROR = "unexpected_internal_error"


class TransientProviderError(Exception):
    """Un proveedor real (Fase 6.3+) la lanza para señalar un fallo
    transitorio (timeout/rate limit/indisponibilidad) — retryable según
    `retry_policy.py`. Ningún `Mock*` la lanza hoy; existe para que
    `run_provider_step` pueda distinguir "vale la pena reintentar" de
    "error interno inesperado" (nunca reintentado) sin acoplarse a un SDK
    concreto todavía inexistente."""

    def __init__(
        self,
        message: str = "",
        *,
        reason: AIGenerationFailureReason = AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
    ) -> None:
        super().__init__(message)
        self.reason = reason
