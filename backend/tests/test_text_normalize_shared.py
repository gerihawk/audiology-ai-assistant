"""Test contractual: `benchmark/metrics/text_normalize.py` reexporta
`app/core/text_normalize.py` sin divergencia semántica — ver
docs/fase-6-rfc.md §5.3 y app/ai_pipeline/domain/grounding.py."""

from __future__ import annotations

from app.core.text_normalize import normalize_text as core_normalize_text
from app.core.text_normalize import normalize_words as core_normalize_words
from benchmark.metrics.text_normalize import normalize_text as benchmark_normalize_text
from benchmark.metrics.text_normalize import normalize_words as benchmark_normalize_words


def test_benchmark_reexporta_exactamente_la_misma_funcion():
    assert benchmark_normalize_text is core_normalize_text
    assert benchmark_normalize_words is core_normalize_words


def test_normalizacion_no_diverge_con_tildes_puntuacion_y_mayusculas():
    casos = [
        "¿El paciente refiere VÉRTIGO ocasional?",
        "Vía aérea, d'Artagnan — otorrea leve.",
        "  espacios   múltiples  ",
        "",
    ]
    for texto in casos:
        assert benchmark_normalize_text(texto) == core_normalize_text(texto)
        assert benchmark_normalize_words(texto) == core_normalize_words(texto)
