"""Tests de PricingTableCostEstimator (Fase 6.3.8) — sin red, sin BD."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.integrations.providers.pricing_table_cost_estimator import (
    MODEL_PRICING,
    PricingTableCostEstimator,
    UnknownModelPricingError,
)


def test_los_tres_modelos_reales_estan_en_la_tabla():
    assert set(MODEL_PRICING) == {"claude-opus-5", "gpt-5.2", "gemini-3.6-flash"}


def test_estimate_con_modelo_conocido_calcula_correctamente():
    estimator = PricingTableCostEstimator()
    cost = estimator.estimate(
        provider="anthropic", model="claude-opus-5", input_tokens=1_000_000, output_tokens=0
    )
    assert cost == Decimal("5.00")


def test_estimate_combina_input_y_output():
    estimator = PricingTableCostEstimator()
    cost = estimator.estimate(
        provider="openai", model="gpt-5.2", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert cost == Decimal("1.75") + Decimal("14.00")


def test_estimate_devuelve_decimal():
    estimator = PricingTableCostEstimator()
    cost = estimator.estimate(
        provider="google", model="gemini-3.6-flash", input_tokens=100, output_tokens=50
    )
    assert isinstance(cost, Decimal)


def test_cero_tokens_con_modelo_conocido_es_cero_legitimo():
    estimator = PricingTableCostEstimator()
    cost = estimator.estimate(
        provider="anthropic", model="claude-opus-5", input_tokens=0, output_tokens=0
    )
    assert cost == Decimal("0")


def test_modelo_desconocido_lanza_en_vez_de_devolver_cero():
    estimator = PricingTableCostEstimator()
    with pytest.raises(UnknownModelPricingError):
        estimator.estimate(
            provider="anthropic",
            model="claude-unreleased-model",
            input_tokens=100,
            output_tokens=50,
        )


def test_modelo_none_lanza_en_vez_de_devolver_cero():
    estimator = PricingTableCostEstimator()
    with pytest.raises(UnknownModelPricingError):
        estimator.estimate(provider="mock", model=None, input_tokens=100, output_tokens=50)
