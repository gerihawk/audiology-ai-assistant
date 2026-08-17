"""`TextDocumentExporter` — Hito 6.6.2/6.7.2 (docs/fase-6-rfc.md §7.1/§7.2/§7.4).

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
from app.export.domain.entities import ExportableDocument, ExportBundle
from app.export.infrastructure.shared import (
    EMPTY_VALUE_PLACEHOLDER,
    RULESET_DISCLAIMER,
    UNEXPLORED_BLOCK_PLACEHOLDER,
    UNSPECIFIED_SESSION_TYPE_LABEL,
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
    """docs/clinical-safety.md §7: obligatorio en todo lugar donde se
    exporten `clinical_flags`, además del aviso general ya cubierto por
    "Aprobado por" en la cabecera — el checklist que las genera no está
    validado clínicamente, con independencia de que el artefacto esté
    aprobado."""
    lines: list[str] = [RULESET_DISCLAIMER, ""]
    flags = content.get("flags") or []
    if not flags:
        lines.append(EMPTY_VALUE_PLACEHOLDER)
        return lines
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


def _lookup_renderer(artifact_type: AIArtifactType) -> Callable[[dict[str, Any]], list[str]]:
    renderer = _BODY_RENDERERS.get(artifact_type)
    if renderer is None:
        raise ValueError(
            f"TextDocumentExporter no sabe renderizar artifact_type={artifact_type!r}."
        )
    return renderer


class TextDocumentExporter:
    """Implementación en texto plano de `DocumentExporter` (hito 6.6.1/
    6.7.2). Renderizado puro en memoria — sin E/S, sin async (ver el
    docstring de `DocumentExporter.export`)."""

    def export(self, document: ExportableDocument) -> bytes:
        renderer = _lookup_renderer(document.artifact_type)
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

    def export_many(self, bundle: ExportBundle) -> bytes:
        """Expediente longitudinal (RFC §7.2, hito 6.7.2): cabecera de
        clínica/paciente una sola vez, luego cada sesión en el orden
        recibido del `bundle` (`clinical_record` ya decidió ese orden,
        ver docstring de `ExportBundle`) con sus documentos separados por
        el mismo bloque de cabecera por documento que usa `export`
        (`header_fields`), reutilizando los mismos `_BODY_RENDERERS`.
        Bundle sin sesiones: se documenta como cabecera sola, sin
        crashear ni inventar una sesión vacía."""
        patient = bundle.patient_internal_code
        if bundle.patient_display_name:
            patient = f"{patient} ({bundle.patient_display_name})"

        lines = [
            "=== HISTORIA CLÍNICA LONGITUDINAL ===",
            f"Clínica: {bundle.clinic_name}",
            f"Paciente: {patient}",
        ]
        for session_index, session in enumerate(bundle.sessions, start=1):
            session_type = session.session_type or UNSPECIFIED_SESSION_TYPE_LABEL
            lines += [
                "",
                f"=== SESIÓN {session_index} ===",
                f"Sesión: {session.clinical_session_id}",
                f"Tipo de sesión: {session_type}",
                f"Fecha de la sesión: {session.created_at.isoformat()}",
            ]
            for document in session.documents:
                renderer = _lookup_renderer(document.artifact_type)
                lines += [
                    "",
                    f"--- {document.artifact_type.value} (v{document.version_number}) ---",
                    *(f"{label}: {value}" for label, value in header_fields(document)),
                    "",
                    *renderer(document.content),
                ]
        return "\n".join(lines).encode("utf-8")
