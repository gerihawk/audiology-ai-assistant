"""Normalización de texto para comparación reference vs. hipótesis.

Implementación movida a `app/core/text_normalize.py` en la Fase 6.1 (ver
docs/fase-6-rfc.md §5.3) para que el runtime de producción
(`ai_pipeline/domain/grounding.py`) y este paquete de benchmark compartan
una única normalización — el dominio de producción no depende de
`benchmark` (evitaría invertir la dependencia), así que es este módulo el
que reexporta desde `app.core`, nunca al revés. Ver
tests/test_text_normalize_shared.py para el test contractual que
garantiza que ambos puntos de entrada no divergen.
"""

from __future__ import annotations

from app.core.text_normalize import normalize_text, normalize_words

__all__ = ["normalize_text", "normalize_words"]
