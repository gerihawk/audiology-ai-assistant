"""Lista versionada de keyterms de audiología para `keyterms_prompt` de
AssemblyAI (Fase 5.2) — ver docs/transcription-benchmark.md §Keyterm
prompting.

**Nunca generada dinámicamente** — mantenida a mano, versionada en git,
testeable por import directo. Cambiar esta lista es un cambio de código
revisable (diff), no una entrada de configuración en tiempo de ejecución.
Si se amplía, sube `KEYTERM_SET_VERSION` para que quede trazable en
`provider_metadata`/`benchmark` qué versión del set se usó en cada
ejecución.
"""

from __future__ import annotations

KEYTERM_SET_VERSION = "audiology-es-v1"

#: Máximo 6 palabras por frase, hasta 1000 términos — límites documentados
#: de `keyterms_prompt` (solo `universal-3-5-pro`), ver
#: docs/transcription-benchmark.md §Keyterm prompting.
AUDIOLOGY_KEYTERMS_ES: list[str] = [
    "hipoacusia",
    "hipoacusia neurosensorial",
    "hipoacusia transmisiva",
    "acúfenos",
    "tinnitus",
    "otitis",
    "otoscopia",
    "audiometría tonal",
    "vía aérea",
    "vía ósea",
    "logoaudiometría",
    "timpanometría",
    "audífonos",
    "ototoxicidad",
    "presbiacusia",
    "oído derecho",
    "oído izquierdo",
]
