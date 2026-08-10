"""Tests de `_content_as_text` (app/ai_pipeline/domain/steps/base.py).

Bug detectado con una llamada real a AssemblyAI (Fase 5): con `segments`
presente en el `content` de `transcript`, `_content_as_text` convertía la
lista entera con `str(value)`, colando sintaxis de Python (`{`,
`'speaker':`, nombres de clave...) en el texto contado por `TokenCounter`
y duplicando aproximadamente el recuento de palabras. Ningún test real
llama a AssemblyAI: se reproduce con un `content` construido a mano,
exactamente con la forma que persiste `TranscriptionStep`.
"""

from __future__ import annotations

from app.ai_pipeline.domain.steps.base import _content_as_text


def test_contenido_solo_con_strings_no_cambia_de_comportamiento():
    content = {"text": "hola mundo", "language": "es"}
    assert _content_as_text(content) == "hola mundo es"


def test_segments_no_inyecta_sintaxis_de_python():
    content = {
        "text": "hola mundo",
        "language": "es",
        "duration_ms": 115000,
        "segments": [{"speaker": "A", "start_ms": 0, "end_ms": 1000, "text": "hola mundo"}],
    }
    result = _content_as_text(content)

    assert "{" not in result
    assert "'speaker'" not in result
    assert "start_ms" not in result
    assert "115000" in result  # el escalar numérico sí se sigue incluyendo


def test_segments_no_infla_el_recuento_con_sintaxis_de_python():
    content = {
        "text": "hola mundo",
        "language": "es",
        "duration_ms": 115000,
        "segments": [{"speaker": "A", "start_ms": 0, "end_ms": 1000, "text": "hola mundo"}],
    }
    # Antes del fix: 13 "palabras" (incluía "{", "'speaker':", "start_ms"...).
    # Tras el fix: solo los valores reales (texto + escalares de cada
    # segmento) — "hola mundo es 115000 A 0 1000 hola mundo". El texto
    # sigue apareciendo dos veces (una vía "text", otra vía "segments"),
    # limitación conocida y documentada — pero ya sin ruido de sintaxis.
    assert len(_content_as_text(content).split()) == 9


def test_varios_segmentos_con_hablantes_distintos():
    content = {
        "text": "Hola. Buenos días.",
        "language": "es",
        "segments": [
            {"speaker": "A", "start_ms": 0, "end_ms": 500, "text": "Hola."},
            {"speaker": "B", "start_ms": 500, "end_ms": 1200, "text": "Buenos días."},
        ],
    }
    result = _content_as_text(content)
    assert "Hola." in result
    assert "Buenos días." in result
    assert "{" not in result


def test_clinical_flags_extrae_los_campos_de_texto_sin_puntuacion_de_python():
    content = {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "Posible tinnitus unilateral.",
                "source_excerpt": "me pita el oído derecho",
                "ruleset_name": "mock-ruleset",
            }
        ]
    }
    result = _content_as_text(content)

    assert "{" not in result
    assert "'category'" not in result
    assert "tinnitus_unilateral" in result
    assert "Posible tinnitus unilateral." in result


def test_lista_vacia_no_lanza_y_no_deja_espacios_sueltos():
    content = {"text": "", "language": "es", "segments": []}
    assert _content_as_text(content) == "es"


def test_segments_none_se_trata_igual_que_ausente():
    content = {"text": "hola", "language": "es", "segments": None}
    result = _content_as_text(content)
    assert result == "hola es None"  # escalar None se sigue convirtiendo con str()
