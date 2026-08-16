"""`TextDocumentExporter` — Hito 6.6.2 (docs/fase-6-rfc.md §7.1/§7.4).

Renderiza un `ExportableDocument` (ya construido y saneado por
`export/domain`, hito 6.6.1) a texto plano UTF-8 legible — nunca JSON
crudo. Sin BD, sin HTTP, sin ORM: opera exclusivamente sobre el DTO ya
resuelto, igual que exige `DocumentExporter` (RFC §7.1: "Ninguna
implementación consulta repositorios directamente ni genera
`AIArtifact`").

El orden de las secciones de `ANAMNESIS`/`SESSION_NOTES` nunca depende de
`dict.items()` — itera siempre sobre las constantes de dominio ya
ordenadas `ANAMNESIS_FIELDS`/`SESSION_NOTES_BLOCKS`, para que el mismo
`content` produzca siempre el mismo texto byte a byte.

Constantes, humanización de nombres de campo y cabecera de metadata viven
en `export/infrastructure/shared.py` — reutilizadas también por
`PdfDocumentExporter` (hito 6.6.3) para que ambos exportadores nunca
diverjan en qué campos muestran, en qué orden, ni en su resolución de
"vacío"/"sin especificar" (RFC §7.1, requisito 6.6.3 punto 9). El layout
del cuerpo (líneas de texto plano) sigue siendo exclusivo de este módulo.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.export.domain.entities import ExportableDocument
from app.export.infrastructure.shared import (
    EMPTY_VALUE_PLACEHOLDER,
    UNEXPLORED_BLOCK_PLACEHOLDER,
    header_fields,
    humanize_field_name,
)
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS

__all__ = ["TextDocumentExporter"]


def _render_prose(content: dict[str, Any]) -> list[str]:
    """`SUMMARY`/`PATIENT_SUMMARY`: `{"text": str}`."""
    return [content["text"]]


def _render_transcript(content: dict[str, Any]) -> list[str]:
    lines = [f"Idioma: {content['language']}"]
    duration_ms = content.get("duration_ms")
    if duration_ms is not None:
        lines.append(f"Duración: {duration_ms} ms")
    lines.append("")
    lines.append("Texto:")
    lines.append(content["text"])

    segments = content.get("segments")
    if segments:
        lines.append("")
        lines.append("Segmentos:")
        for segment in segments:
            speaker = segment.get("speaker") or "?"
            lines.append(
                f"[{segment['start_ms']}-{segment['end_ms']}] {speaker}: {segment['text']}"
            )
    return lines


def _render_clinical_flags(content: dict[str, Any]) -> list[str]:
    flags = content.get("flags") or []
    if not flags:
        return [EMPTY_VALUE_PLACEHOLDER]
    lines: list[str] = []
    for flag in flags:
        lines.append(f"- [{flag['category']}] {flag['description']} ({flag['ruleset_name']})")
    return lines


def _render_missing_information(content: dict[str, Any]) -> list[str]:
    items = content.get("items") or []
    if not items:
        return [EMPTY_VALUE_PLACEHOLDER]
    lines: list[str] = []
    for item in items:
        lines.append(f"- Tema: {item['topic']}")
        lines.append(f"  Pregunta sugerida: {item['suggested_question']}")
    return lines


def _render_anamnesis(content: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for field_name in ANAMNESIS_FIELDS:
        field = content.get(field_name)
        if field is None:
            continue
        value = field.get("value") or EMPTY_VALUE_PLACEHOLDER
        lines.append(f"{humanize_field_name(field_name)} [{field['status']}]:")
        lines.append(value)
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_session_notes(content: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for block_name in SESSION_NOTES_BLOCKS:
        block = content.get(block_name)
        if block is None:
            continue
        text = block.get("text") or UNEXPLORED_BLOCK_PLACEHOLDER
        lines.append(f"{humanize_field_name(block_name)}:")
        lines.append(text)
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


_BODY_RENDERERS: dict[AIArtifactType, Callable[[dict[str, Any]], list[str]]] = {
    AIArtifactType.TRANSCRIPT: _render_transcript,
    AIArtifactType.SUMMARY: _render_prose,
    AIArtifactType.PATIENT_SUMMARY: _render_prose,
    AIArtifactType.CLINICAL_FLAGS: _render_clinical_flags,
    AIArtifactType.MISSING_INFORMATION: _render_missing_information,
    AIArtifactType.ANAMNESIS: _render_anamnesis,
    AIArtifactType.SESSION_NOTES: _render_session_notes,
}


class TextDocumentExporter:
    """Implementación en texto plano de `DocumentExporter` (hito 6.6.1).
    Renderizado puro en memoria — sin E/S, sin async (ver el docstring de
    `DocumentExporter.export`)."""

    def export(self, document: ExportableDocument) -> bytes:
        renderer = _BODY_RENDERERS.get(document.artifact_type)
        if renderer is None:
            raise ValueError(
                f"TextDocumentExporter no sabe renderizar artifact_type="
                f"{document.artifact_type!r}."
            )
        header_lines = [
            "=== DOCUMENTO CLÍNICO EXPORTADO ===",
            *(f"{label}: {value}" for label, value in header_fields(document)),
        ]
        lines = [
            *header_lines,
            "",
            "--- CONTENIDO ---",
            "",
            *renderer(document.content),
        ]
        return "\n".join(lines).encode("utf-8")
