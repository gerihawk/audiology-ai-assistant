"""Tests de `app.core.text_normalize` — sin cobertura dedicada hasta
ahora (solo el contrato de equivalencia con `benchmark/metrics/text_normalize.py`
en `test_text_normalize_shared.py`). Añadidos tras el diagnóstico
post-mortem de la ronda de benchmark del 2026-08-12: `/` no se trataba
como separador, fusionando artificialmente dos tokens (`pitido/acúfeno`
-> `pitido/acúfeno` en vez de `pitido acúfeno`) e impidiendo que
`_matches_any`/`evaluate_negations`/`GroundingValidator` (matching por
palabra completa) encontraran ninguno de los dos términos."""

from __future__ import annotations

from app.core.text_normalize import normalize_text, normalize_words


class TestSlashSeparator:
    def test_pitido_acufeno_permite_matchear_pitido(self):
        normalized = normalize_text("pitido/acúfeno constante")
        assert " pitido " in f" {normalized} "

    def test_pitido_acufeno_permite_matchear_acufeno(self):
        normalized = normalize_text("pitido/acúfeno constante")
        assert " acúfeno " in f" {normalized} "

    def test_via_aerea_via_osea_conserva_tokens_separados(self):
        normalized = normalize_text("audiometría por vía aérea/vía ósea")
        assert normalize_words(normalized) == [
            "audiometría",
            "por",
            "vía",
            "aérea",
            "vía",
            "ósea",
        ]

    def test_derecho_izquierdo_no_se_fusiona(self):
        normalized = normalize_text("oído derecho/izquierdo")
        words = normalize_words(normalized)
        assert "derecho" in words
        assert "izquierdo" in words
        assert "derecho/izquierdo" not in words
        assert "derechoizquierdo" not in words


class TestExistingPunctuationUnaffected:
    """El cambio es una extensión mínima de la misma categoría de
    puntuación de frase ya tratada — no debe alterar el comportamiento ya
    verificado para el resto de signos."""

    def test_guion_interno_de_palabra_compuesta_se_conserva(self):
        assert normalize_text("vía-aérea") == "vía-aérea"

    def test_apostrofo_interno_se_conserva(self):
        assert normalize_text("d'Artagnan") == "d'artagnan"

    def test_coma_punto_y_coma_dos_puntos_parentesis_siguen_siendo_separadores(self):
        assert normalize_text("sin cirugía; sin alergias") == "sin cirugía sin alergias"
        assert normalize_text("hipoacusia (neurosensorial)") == "hipoacusia neurosensorial"
        assert normalize_text("oído izquierdo, oído derecho") == "oído izquierdo oído derecho"

    def test_tildes_mayusculas_espacios_sin_cambios(self):
        assert normalize_text("  Pérdida  AUDITIVA  ") == "pérdida auditiva"
