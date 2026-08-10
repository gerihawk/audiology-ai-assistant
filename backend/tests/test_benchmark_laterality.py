"""Tests de la métrica de lateralidad (benchmark/metrics/laterality.py)."""

from __future__ import annotations

from benchmark.dataset_metadata import LateralityCase
from benchmark.metrics.laterality import evaluate_laterality

_TINNITUS_LEFT = LateralityCase(
    concept="tinnitus",
    laterality="left",
    patterns={
        "left": ["oído izquierdo", "izquierdo"],
        "right": ["oído derecho", "derecho"],
        "bilateral": ["ambos oídos", "los dos oídos", "bilateral"],
    },
)


def test_lateralidad_correcta_pasa():
    report = evaluate_laterality("el pitido es más intenso en el oído izquierdo", [_TINNITUS_LEFT])
    assert report.passed == 1
    assert report.failed == 0
    assert report.details[0].matched_laterality == "left"


def test_lateralidad_invertida_falla():
    report = evaluate_laterality("el pitido es más intenso en el oído derecho", [_TINNITUS_LEFT])
    assert report.failed == 1
    assert report.details[0].matched_laterality == "right"


def test_lateralidad_no_detectada():
    report = evaluate_laterality("el paciente refiere acúfenos", [_TINNITUS_LEFT])
    assert report.passed == 0
    assert report.failed == 0
    assert report.details[0].result == "not_detected"


def test_bilateral_esperado_y_detectado():
    case = LateralityCase(
        concept="hearing_loss",
        laterality="bilateral",
        patterns={
            "left": ["oído izquierdo"],
            "right": ["oído derecho"],
            "bilateral": ["ambos oídos", "los dos oídos"],
        },
    )
    report = evaluate_laterality("pérdida de audición en los dos oídos", [case])
    assert report.passed == 1


def test_bilateral_esperado_pero_solo_detecta_un_lado_falla():
    case = LateralityCase(
        concept="hearing_loss",
        laterality="bilateral",
        patterns={
            "left": ["oído izquierdo"],
            "right": ["oído derecho"],
            "bilateral": ["ambos oídos", "los dos oídos"],
        },
    )
    report = evaluate_laterality("pérdida de audición en el oído izquierdo", [case])
    assert report.failed == 1
    assert report.details[0].matched_laterality == "left"
