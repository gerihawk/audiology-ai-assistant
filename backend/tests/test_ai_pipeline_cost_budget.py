"""Tests de `SessionCostBudget` (app/ai_pipeline/domain/cost_budget.py) —
ver docs/fase-6-rfc.md §6.3."""

from __future__ import annotations

from decimal import Decimal

from app.ai_pipeline.domain.cost_budget import SessionCostBudget


def test_limite_desactivado_nunca_bloquea():
    budget = SessionCostBudget(limit_usd=None, accumulated_usd=Decimal("999"))
    assert budget.would_exceed(Decimal("1000")) is False
    assert budget.remaining_usd() is None


def test_potencial_dentro_del_limite_no_bloquea():
    budget = SessionCostBudget(limit_usd=Decimal("1.00"), accumulated_usd=Decimal("0.20"))
    assert budget.would_exceed(Decimal("0.50")) is False


def test_potencial_que_supera_el_limite_bloquea():
    budget = SessionCostBudget(limit_usd=Decimal("1.00"), accumulated_usd=Decimal("0.80"))
    assert budget.would_exceed(Decimal("0.30")) is True


def test_potencial_exactamente_en_el_limite_no_bloquea():
    budget = SessionCostBudget(limit_usd=Decimal("1.00"), accumulated_usd=Decimal("0.70"))
    assert budget.would_exceed(Decimal("0.30")) is False


def test_record_acumula_coste_real_para_la_siguiente_comprobacion():
    budget = SessionCostBudget(limit_usd=Decimal("1.00"))
    budget.record(Decimal("0.60"))
    budget.record(Decimal("0.30"))
    assert budget.accumulated_usd == Decimal("0.90")
    assert budget.remaining_usd() == Decimal("0.10")
    assert budget.would_exceed(Decimal("0.20")) is True


def test_cada_instancia_parte_de_coste_acumulado_independiente():
    a = SessionCostBudget(limit_usd=Decimal("1.00"))
    b = SessionCostBudget(limit_usd=Decimal("1.00"))
    a.record(Decimal("0.50"))
    assert b.accumulated_usd == Decimal("0")
