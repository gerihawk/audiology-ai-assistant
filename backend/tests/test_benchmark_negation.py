"""Tests de la métrica de negaciones (benchmark/metrics/negation.py)."""

from __future__ import annotations

from benchmark.dataset_metadata import NegationCase
from benchmark.metrics.negation import evaluate_negations

_VERTIGO_CASE = NegationCase(
    concept="vertigo",
    expected="negated",
    patterns={
        "negated": ["no tiene vértigo", "no vértigo", "niega vértigo"],
        "affirmed": ["tiene vértigo", "sí vértigo", "refiere vértigo"],
    },
)


def test_negacion_correctamente_preservada_pasa():
    report = evaluate_negations("el paciente no tiene vértigo ni mareos", [_VERTIGO_CASE])
    assert report.passed == 1
    assert report.failed == 0
    assert report.details[0].result == "pass"
    assert report.details[0].matched_pattern == "no tiene vértigo"


def test_negacion_invertida_falla():
    # El caso grave que pide detectar el encargo: "no tiene vértigo" -> "tiene vértigo".
    report = evaluate_negations("el paciente tiene vértigo ocasional", [_VERTIGO_CASE])
    assert report.passed == 0
    assert report.failed == 1
    assert report.details[0].result == "fail"


def test_negacion_no_detectada_ni_pasa_ni_falla():
    report = evaluate_negations("el paciente refiere acúfenos", [_VERTIGO_CASE])
    assert report.passed == 0
    assert report.failed == 0
    assert report.details[0].result == "not_detected"


def test_caso_de_afirmacion_esperada():
    case = NegationCase(
        concept="tinnitus",
        expected="affirmed",
        patterns={
            "affirmed": ["tiene acúfenos", "refiere acúfenos"],
            "negated": ["no tiene acúfenos", "niega acúfenos"],
        },
    )
    passed = evaluate_negations("el paciente refiere acúfenos constantes", [case])
    assert passed.passed == 1

    failed = evaluate_negations("el paciente niega acúfenos", [case])
    assert failed.failed == 1


def test_varios_casos_mezcla_pass_fail_not_detected():
    hearing_aid_case = NegationCase(
        concept="hearing_aid_use",
        expected="negated",
        patterns={
            "negated": ["nunca ha utilizado audífonos"],
            "affirmed": ["utiliza audífonos"],
        },
    )
    report = evaluate_negations(
        "el paciente no tiene vértigo y utiliza audífonos desde hace un año",
        [_VERTIGO_CASE, hearing_aid_case],
    )
    assert report.passed == 1
    assert report.failed == 1
