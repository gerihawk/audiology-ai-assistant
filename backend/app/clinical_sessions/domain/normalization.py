"""Normalización de texto compartida entre los esquemas de entrada y el servicio."""

from __future__ import annotations


def normalize_free_text(value: str) -> str:
    """Recorta y colapsa espacios internos de un campo de texto libre."""
    return " ".join(value.split())
