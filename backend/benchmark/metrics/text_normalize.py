"""Normalización de texto para comparación reference vs. hipótesis.

Ver docs/transcription-benchmark.md §WER — normalización documentada
explícitamente: minúsculas, Unicode NFC, puntuación separada de las
palabras (nunca eliminada de forma agresiva: un apóstrofo o guion dentro
de una palabra se conserva, ya que puede ser semánticamente relevante —
p. ej. "vía aérea" no debe perder sus tildes ni fusionarse con la palabra
siguiente), espacios colapsados.
"""

from __future__ import annotations

import re
import unicodedata

#: Puntuación que se retira SOLO cuando actúa como separador (rodeada de
#: espacio o en un borde de palabra) — nunca dentro de un token como
#: "vía-aérea" o "d'Artagnan", que se conservan tal cual.
_PUNCTUATION_PATTERN = re.compile(r"[¿?¡!.,;:()\"“”«»\[\]{}]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """minúsculas -> NFC -> puntuación de frase retirada -> espacios colapsados.

    No elimina tildes, ni guiones/apóstrofos internos de una palabra, ni
    dígitos — solo la puntuación que delimita frases/preguntas. Ver
    docs/transcription-benchmark.md §WER para la justificación de no
    normalizar de forma más agresiva.
    """
    normalized = unicodedata.normalize("NFC", text.lower())
    normalized = _PUNCTUATION_PATTERN.sub(" ", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized


def normalize_words(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split(" ") if normalized else []
