"""Tests de WER (benchmark/metrics/wer.py, alignment.py, text_normalize.py)."""

from __future__ import annotations

from benchmark.metrics.alignment import align_words
from benchmark.metrics.text_normalize import normalize_text, normalize_words
from benchmark.metrics.wer import compute_wer


def test_wer_perfecto_es_cero():
    result = compute_wer("hola mundo, ¿cómo estás?", "hola mundo, ¿cómo estás?")
    assert result.value == 0.0
    assert result.substitutions == 0
    assert result.deletions == 0
    assert result.insertions == 0


def test_wer_con_sustitucion():
    result = compute_wer("el paciente tiene vértigo", "el paciente tiene mareo")
    assert result.substitutions == 1
    assert result.deletions == 0
    assert result.insertions == 0
    assert result.reference_word_count == 4
    assert result.value == 1 / 4


def test_wer_con_eliminacion():
    result = compute_wer("el paciente refiere acúfenos leves", "el paciente refiere acúfenos")
    assert result.deletions == 1
    assert result.substitutions == 0
    assert result.insertions == 0
    assert result.value == 1 / 5


def test_wer_con_insercion():
    result = compute_wer("el paciente refiere acúfenos", "el paciente también refiere acúfenos")
    assert result.insertions == 1
    assert result.substitutions == 0
    assert result.deletions == 0
    assert result.value == 1 / 4


def test_wer_referencia_vacia_no_divide_por_cero():
    result = compute_wer("", "algo")
    assert result.reference_word_count == 0
    assert result.value == 0.0


def test_normalizacion_unicode_acentos_se_conservan():
    # Las tildes SÍ importan semánticamente en español — normalize_text
    # nunca las retira, solo normaliza a NFC.
    assert normalize_text("acúfenos") == "acúfenos"
    assert normalize_text("Acúfenos") == "acúfenos"


def test_normalizacion_puntuacion_no_afecta_al_wer():
    result = compute_wer("¿Tiene vértigo?", "tiene vertigo")
    # Sin tildes en la hipótesis: "vértigo" != "vertigo" -> 1 sustitución,
    # pero la puntuación de frase (¿, ?) no debe contar como error.
    assert result.reference_word_count == 2
    assert result.substitutions == 1


def test_normalizacion_espacios_multiples_se_colapsan():
    assert normalize_words("hola    mundo") == ["hola", "mundo"]


def test_normalizacion_no_elimina_digitos_ni_guiones_internos():
    assert normalize_text("tiene 8-9 meses") == "tiene 8-9 meses"


def test_alineacion_devuelve_operaciones_en_orden():
    ops = align_words(["a", "b", "c"], ["a", "x", "c"])
    assert [op.op for op in ops] == ["match", "sub", "match"]
    assert ops[1].ref_word == "b"
    assert ops[1].hyp_word == "x"
