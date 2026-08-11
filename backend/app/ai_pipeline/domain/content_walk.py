"""Recorrido genérico de un `content` de `AIArtifactVersion` (dict JSON
anidado con dicts/listas/escalares) para localizar sus valores string de
hoja, con una ruta legible (`flags[0].description`) para poder señalar
"ubicación/campo" en violaciones de `SafetyValidator` y en la detección de
respuesta evasiva/meta — ver docs/fase-6-rfc.md §5.2."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def iter_string_leaves(content: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(content, str):
        if content:
            yield path, content
        return
    if isinstance(content, dict):
        for key, value in content.items():
            child_path = f"{path}.{key}" if path else key
            yield from iter_string_leaves(value, child_path)
        return
    if isinstance(content, list):
        for index, value in enumerate(content):
            yield from iter_string_leaves(value, f"{path}[{index}]")


def iter_dict_nodes(content: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """Todo nodo dict a cualquier profundidad (incluida la raíz), con su
    ruta — usado por `validation_pipeline.py` para localizar bloques que
    declaran `source_excerpt` sin asumir la forma de un `artifact_type`
    concreto."""
    if isinstance(content, dict):
        yield path, content
        for key, value in content.items():
            child_path = f"{path}.{key}" if path else key
            yield from iter_dict_nodes(value, child_path)
        return
    if isinstance(content, list):
        for index, value in enumerate(content):
            yield from iter_dict_nodes(value, f"{path}[{index}]")
