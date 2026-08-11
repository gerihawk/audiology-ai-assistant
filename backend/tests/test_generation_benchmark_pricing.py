"""Tests de `pricing.estimate_cost` — Fase 6.2. Nunca mezcla coste
reportado por el proveedor con la tabla local (encargo §16)."""

from __future__ import annotations

from decimal import Decimal

from benchmark.generation.pricing import CostEstimateSource, estimate_cost


def test_coste_reportado_por_el_proveedor_tiene_prioridad():
    result = estimate_cost(
        model="anthropic/claude-sonnet-5",
        input_tokens=1000,
        output_tokens=200,
        provider_reported_cost_usd="0.0034",
    )
    assert result.source == CostEstimateSource.PROVIDER
    assert result.amount_usd == Decimal("0.0034")
    assert result.pricing_version is None


def test_tabla_local_se_usa_si_no_hay_coste_del_proveedor():
    result = estimate_cost(
        model="anthropic/claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        provider_reported_cost_usd=None,
    )
    assert result.source == CostEstimateSource.PRICING_TABLE
    assert result.amount_usd == Decimal("12.00")  # 2.00 + 10.00 por millón
    assert result.pricing_version is not None


def test_modelo_desconocido_nunca_inventa_un_precio():
    result = estimate_cost(
        model="proveedor/modelo-no-registrado",
        input_tokens=100,
        output_tokens=100,
        provider_reported_cost_usd=None,
    )
    assert result.source == CostEstimateSource.UNKNOWN
    assert result.amount_usd is None


def test_sin_tokens_conocidos_nunca_inventa_un_precio():
    result = estimate_cost(
        model="anthropic/claude-sonnet-5",
        input_tokens=None,
        output_tokens=None,
        provider_reported_cost_usd=None,
    )
    assert result.source == CostEstimateSource.UNKNOWN
    assert result.amount_usd is None
