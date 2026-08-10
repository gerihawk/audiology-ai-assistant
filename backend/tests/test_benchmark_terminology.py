"""Tests de la métrica de terminología (benchmark/metrics/terminology.py)."""

from __future__ import annotations

from benchmark.metrics.terminology import evaluate_terminology


def test_termino_simple_reconocido():
    report = evaluate_terminology(
        "el paciente refiere acúfenos leves", "el paciente refiere acúfenos leves", ["acúfenos"]
    )
    assert report.accuracy == 1.0
    assert report.details[0].status == "recognized"
    assert report.details[0].present_in_reference is True


def test_termino_multi_palabra_reconocido():
    report = evaluate_terminology(
        "vamos a realizar una audiometría tonal por vía aérea y vía ósea",
        "vamos a realizar una audiometría tonal por vía aérea y vía ósea",
        ["audiometría tonal", "vía aérea", "vía ósea"],
    )
    assert report.accuracy == 1.0
    assert all(d.status == "recognized" for d in report.details)


def test_termino_omitido():
    report = evaluate_terminology(
        "el paciente refiere hipoacusia progresiva",
        "el paciente refiere pérdida auditiva progresiva",
        ["hipoacusia"],
    )
    assert report.details[0].status == "omitted"
    assert report.accuracy == 0.0


def test_termino_multi_palabra_sustituido_por_solapamiento_parcial():
    report = evaluate_terminology(
        "necesita una audiometría tonal completa",
        "necesita una audiometría completa",  # falta "tonal" pero "audiometría" sí aparece
        ["audiometría tonal"],
    )
    assert report.details[0].status == "substituted"


def test_termino_no_presente_en_referencia_se_marca_no_aplicable():
    report = evaluate_terminology(
        "el paciente refiere acúfenos", "el paciente refiere acúfenos", ["vértigo"]
    )
    assert report.details[0].status == "not_in_reference"
    assert report.details[0].present_in_reference is False
    # No aplicable no debe contar ni a favor ni en contra de accuracy.
    assert report.accuracy is None


def test_sin_terminos_aplicables_accuracy_es_none():
    report = evaluate_terminology("texto cualquiera", "texto cualquiera", ["inexistente"])
    assert report.accuracy is None


def test_no_confunde_subcadenas_parciales_de_palabra():
    # "vía" no debe reconocerse dentro de "desvía" o similar.
    report = evaluate_terminology("el sonido se desvía mucho", "el sonido se desvía mucho", ["vía"])
    assert report.details[0].present_in_reference is False


def test_varios_terminos_mezcla_de_estados():
    report = evaluate_terminology(
        reference_text="tiene hipoacusia, acúfenos y antecedentes familiares",
        hypothesis_text="tiene pérdida auditiva y antecedentes familiares",
        terms=["hipoacusia", "acúfenos", "antecedentes familiares"],
    )
    statuses = {d.term: d.status for d in report.details}
    assert statuses["hipoacusia"] == "omitted"
    assert statuses["acúfenos"] == "omitted"
    assert statuses["antecedentes familiares"] == "recognized"
    assert report.accuracy == 1 / 3
