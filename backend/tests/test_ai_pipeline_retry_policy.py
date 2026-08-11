"""Tests de la política de reintentos (app/ai_pipeline/domain/retry_policy.py)
— ver docs/fase-6-rfc.md §5.5."""

from __future__ import annotations

import pytest

from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.retry_policy import backoff_seconds, max_retries_for

_GENERAL = (
    AIGenerationFailureReason.PROVIDER_TIMEOUT,
    AIGenerationFailureReason.PROVIDER_RATE_LIMITED,
    AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
    AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
    AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED,
    AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE,
)
_REGENERATIVE = (
    AIGenerationFailureReason.GROUNDING_FAILED,
    AIGenerationFailureReason.SAFETY_POLICY_FAILED,
)
_NEVER = (
    AIGenerationFailureReason.COST_LIMIT_EXCEEDED,
    AIGenerationFailureReason.UNEXPECTED_INTERNAL_ERROR,
)


@pytest.mark.parametrize("reason", _GENERAL)
def test_fallos_generales_admiten_max_general_reintentos(reason):
    assert max_retries_for(reason, max_general=2, max_regenerative=1) == 2


@pytest.mark.parametrize("reason", _REGENERATIVE)
def test_fallos_regenerativos_admiten_como_mucho_max_regenerative(reason):
    assert max_retries_for(reason, max_general=2, max_regenerative=1) == 1


@pytest.mark.parametrize("reason", _NEVER)
def test_fallos_no_retryable_nunca_se_reintentan(reason):
    assert max_retries_for(reason, max_general=2, max_regenerative=1) == 0


def test_max_retries_respeta_la_configuracion_recibida():
    assert (
        max_retries_for(
            AIGenerationFailureReason.PROVIDER_TIMEOUT, max_general=0, max_regenerative=0
        )
        == 0
    )


def test_backoff_desactivado_con_base_cero():
    assert backoff_seconds(0, base_seconds=0.0) == 0.0
    assert backoff_seconds(3, base_seconds=0.0) == 0.0


def test_backoff_crece_de_forma_acotada_con_el_intento():
    for attempt in range(4):
        value = backoff_seconds(attempt, base_seconds=0.1)
        low = 0.1 * (2**attempt)
        high = low + 0.1
        assert low <= value <= high
