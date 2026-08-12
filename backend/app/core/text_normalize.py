"""Normalización de texto compartida entre `benchmark` y el runtime de producción.

Extraída de `benchmark/metrics/text_normalize.py` (Fase 5) para que
`ai_pipeline/domain/grounding.py` (Fase 6.1) no dependa del paquete
`benchmark` — ver docs/fase-6-rfc.md §5.3: "reutiliza una única
normalización equivalente a benchmark/metrics/text_normalize.py; la
implementación debe extraer esa normalización a una utilidad compartida o
garantizar mediante tests contractuales que ambas no divergen". Aquí vive
la única implementación; `benchmark/metrics/text_normalize.py` reexporta
estos mismos símbolos.

minúsculas -> NFC -> puntuación de frase retirada -> espacios colapsados.
No elimina tildes, ni guiones/apóstrofos internos de una palabra, ni
dígitos — solo la puntuación que delimita frases/preguntas. Ver
docs/transcription-benchmark.md §WER para la justificación de no
normalizar de forma más agresiva.
"""

from __future__ import annotations

import re
import unicodedata

#: Puntuación que se retira SOLO cuando actúa como separador (rodeada de
#: espacio o en un borde de palabra) — nunca dentro de un token como
#: "vía-aérea" o "d'Artagnan", que se conservan tal cual. `/` se incluye
#: aquí (no junto a los guiones): a diferencia del guion interno de una
#: palabra compuesta, `/` en español clínico siempre separa dos términos
#: distintos ("pitido/acúfeno", "vía aérea/vía ósea") — nunca forma parte
#: de un único token — así que debe convertirse en espacio como el resto
#: de puntuación de frase, o fusiona artificialmente dos palabras en una
#: que ningún patrón de metadata puede matchear (diagnóstico post-mortem
#: 2026-08-12, ver docs/generation-benchmark.md §9.5).
_PUNCTUATION_PATTERN = re.compile(r"[¿?¡!.,;:()\"“”«»\[\]{}/]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text.lower())
    normalized = _PUNCTUATION_PATTERN.sub(" ", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized


def normalize_words(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split(" ") if normalized else []
