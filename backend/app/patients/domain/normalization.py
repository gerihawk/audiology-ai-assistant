"""Normalización de texto compartida entre los esquemas de entrada y el servicio."""

from __future__ import annotations

import re

_INTERNAL_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def normalize_internal_code(value: str) -> str:
    normalized = value.strip()
    if not normalized or not _INTERNAL_CODE_PATTERN.match(normalized):
        raise ValueError("internal_code solo admite letras, números, '.', '_' y '-', sin espacios.")
    return normalized


def normalize_free_text(value: str) -> str:
    """Recorta y colapsa espacios internos de un campo de texto libre."""
    return " ".join(value.split())
