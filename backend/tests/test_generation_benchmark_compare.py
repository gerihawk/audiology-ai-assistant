"""Tests de `compare.py` — Fase 6.2. Nunca ejecuta generación, solo
agrega resultados ya escritos. Selección de ganador jerárquica y sin
forzar un ganador global entre `artifact_type` distintos (encargo,
precondición §13-14)."""

from __future__ import annotations

from benchmark.generation.compare import build_comparison, select_winner_per_artifact_type


def _report(**overrides) -> dict:
    defaults = {
        "artifact_type": "summary",
        "model": "openai/gpt-test",
        "gates": {
            "passed_all": True,
            "blocking_gate": None,
            "safety_gate": True,
            "hallucination_gate": True,
            "schema_gate": True,
            "negation_laterality_gate": True,
        },
        "execution": {
            "latency_ms": 1000,
            "input_tokens": 100,
            "output_tokens": 20,
            "estimated_cost_usd": "0.01",
            "cost_source": "pricing_table",
        },
        "findings": [],
    }
    defaults.update(overrides)
    return defaults


class TestBuildComparison:
    def test_sin_resultados(self):
        comparison = build_comparison("caso_1", {})
        assert comparison["models"] == []
        assert comparison["winner"] is None

    def test_gana_quien_supera_gates_con_menos_hallazgos_major(self):
        results = {
            "modelo_a": _report(
                findings=[{"severity": "major", "category": "omission", "description": "x"}]
            ),
            "modelo_b": _report(),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] == "modelo_b"

    def test_modelo_que_no_pasa_gates_nunca_gana_aunque_sea_mas_barato(self):
        results = {
            "modelo_barato_pero_inseguro": _report(
                gates={
                    "passed_all": False,
                    "blocking_gate": "safety",
                    "safety_gate": False,
                    "hallucination_gate": None,
                    "schema_gate": True,
                    "negation_laterality_gate": None,
                },
                execution={
                    "latency_ms": 500,
                    "input_tokens": 50,
                    "output_tokens": 10,
                    "estimated_cost_usd": "0.001",
                    "cost_source": "pricing_table",
                },
            ),
            "modelo_caro_pero_seguro": _report(
                execution={
                    "latency_ms": 3000,
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "estimated_cost_usd": "0.05",
                    "cost_source": "pricing_table",
                },
            ),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] == "modelo_caro_pero_seguro"

    def test_empate_en_hallazgos_lo_decide_el_coste(self):
        results = {
            "modelo_caro": _report(
                execution={
                    "latency_ms": 1000,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "estimated_cost_usd": "0.10",
                    "cost_source": "pricing_table",
                },
            ),
            "modelo_barato": _report(
                execution={
                    "latency_ms": 1000,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "estimated_cost_usd": "0.01",
                    "cost_source": "pricing_table",
                },
            ),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] == "modelo_barato"

    def test_criterio_oficial_retries_desempata_antes_que_latencia_y_coste(self):
        # Menos hallazgos empatados; el modelo con MENOS retries gana
        # aunque tenga mayor latencia Y mayor coste — orden oficial fijado
        # en el diagnóstico post-mortem 2026-08-12 (calidad -> retries ->
        # latencia -> coste), nunca coste primero.
        results = {
            "mas_retries_pero_barato_y_rapido": _report(
                execution={
                    "attempts": 3,
                    "latency_ms": 500,
                    "estimated_cost_usd": "0.01",
                    "cost_source": "pricing_table",
                },
            ),
            "menos_retries_pero_caro_y_lento": _report(
                execution={
                    "attempts": 1,
                    "latency_ms": 9000,
                    "estimated_cost_usd": "0.50",
                    "cost_source": "pricing_table",
                },
            ),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] == "menos_retries_pero_caro_y_lento"

    def test_criterio_oficial_latencia_desempata_antes_que_coste_cuando_retries_empatan(self):
        results = {
            "mas_barato_pero_lento": _report(
                execution={
                    "attempts": 1,
                    "latency_ms": 9000,
                    "estimated_cost_usd": "0.01",
                    "cost_source": "pricing_table",
                },
            ),
            "mas_caro_pero_rapido": _report(
                execution={
                    "attempts": 1,
                    "latency_ms": 500,
                    "estimated_cost_usd": "0.50",
                    "cost_source": "pricing_table",
                },
            ),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] == "mas_caro_pero_rapido"

    def test_ningun_modelo_pasa_los_gates_no_hay_ganador(self):
        results = {
            "modelo_a": _report(
                gates={
                    "passed_all": False,
                    "blocking_gate": "schema",
                    "safety_gate": True,
                    "hallucination_gate": None,
                    "schema_gate": False,
                    "negation_laterality_gate": None,
                }
            ),
        }
        comparison = build_comparison("caso_1", results)
        assert comparison["winner"] is None


class TestSelectWinnerPerArtifactType:
    def test_ganador_global_solo_si_el_mismo_modelo_gana_en_todos(self):
        comparisons = {
            "summary": {"winner": "modelo_a"},
            "missing_information": {"winner": "modelo_a"},
            "patient_summary": {"winner": "modelo_a"},
        }
        summary = select_winner_per_artifact_type(comparisons)
        assert summary["global_winner"] == "modelo_a"

    def test_sin_ganador_global_si_los_ganadores_difieren(self):
        comparisons = {
            "summary": {"winner": "modelo_a"},
            "missing_information": {"winner": "modelo_b"},
            "patient_summary": {"winner": "modelo_a"},
        }
        summary = select_winner_per_artifact_type(comparisons)
        assert summary["global_winner"] is None
        assert summary["winners_by_artifact_type"] == {
            "summary": "modelo_a",
            "missing_information": "modelo_b",
            "patient_summary": "modelo_a",
        }

    def test_sin_ganador_global_si_algun_artifact_type_no_tiene_ganador(self):
        comparisons = {
            "summary": {"winner": "modelo_a"},
            "missing_information": {"winner": None},
        }
        summary = select_winner_per_artifact_type(comparisons)
        assert summary["global_winner"] is None
