"""`PdfDocumentExporter` — Hito 6.6.3 (docs/fase-6-rfc.md §7.1/§7.4).

Renderiza un `ExportableDocument` a PDF legible — nunca JSON crudo. Sin
BD, sin HTTP, sin ORM, sin ficheros temporales: `SimpleDocTemplate` de
ReportLab escribe sobre un `io.BytesIO()` en memoria y `export()` devuelve
`buffer.getvalue()` directamente.

Misma interpretación clínica que `TextDocumentExporter` (RFC §7.1,
requisito 6.6.3 punto 9): reutiliza de `export/infrastructure/shared.py`
las mismas constantes de placeholder, la misma humanización de nombres de
campo y la misma cabecera de metadata, y recorre los mismos
`ANAMNESIS_FIELDS`/`SESSION_NOTES_BLOCKS` en el mismo orden — nunca
`dict.items()`. El layout es propio de PDF (encabezados/párrafos de
Platypus) y deliberadamente no comparte funciones de cuerpo con el TXT:
unificar ambos layouts físicos en una única abstracción de renderizado no
es necesario (ver docstring de `shared.py`).

Fuentes base14 de ReportLab (Helvetica) únicamente — cubren ñ, tildes,
¿/¡ y ü vía WinAnsiEncoding sin necesitar ningún asset de fuente
embebido. Todo texto proveniente de `content` se escapa con
`xml.sax.saxutils.escape` antes de pasarlo a `Paragraph`, que interpreta
un subconjunto de XML/HTML — sin escapar, un valor clínico con `<`/`>`/`&`
literales rompería el parseo o alteraría el documento.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import StyleSheet1, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.ai_pipeline.domain.entities import AIArtifactType
from app.export.domain.entities import ExportableDocument
from app.export.infrastructure.shared import (
    EMPTY_VALUE_PLACEHOLDER,
    RULESET_DISCLAIMER,
    UNEXPLORED_BLOCK_PLACEHOLDER,
    header_fields,
    humanize_field_name,
)
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS

__all__ = ["PdfDocumentExporter"]

_SECTION_SPACING = 6
_ITEM_SPACING = 4


def _render_prose(content: dict[str, Any], styles: StyleSheet1) -> list:
    """`SUMMARY`/`PATIENT_SUMMARY`: `{"text": str}`."""
    return [Paragraph(escape(content["text"]), styles["Normal"])]


def _render_transcript(content: dict[str, Any], styles: StyleSheet1) -> list:
    flowables = [Paragraph(f"<b>Idioma:</b> {escape(content['language'])}", styles["Normal"])]
    duration_ms = content.get("duration_ms")
    if duration_ms is not None:
        flowables.append(Paragraph(f"<b>Duración:</b> {duration_ms} ms", styles["Normal"]))
    flowables.append(Spacer(1, _SECTION_SPACING))
    flowables.append(Paragraph("Texto", styles["Heading3"]))
    flowables.append(Paragraph(escape(content["text"]), styles["Normal"]))

    segments = content.get("segments")
    if segments:
        flowables.append(Spacer(1, _SECTION_SPACING))
        flowables.append(Paragraph("Segmentos", styles["Heading3"]))
        for segment in segments:
            speaker = segment.get("speaker") or "?"
            line = f"[{segment['start_ms']}-{segment['end_ms']}] {speaker}: {segment['text']}"
            flowables.append(Paragraph(escape(line), styles["Normal"]))
    return flowables


def _render_clinical_flags(content: dict[str, Any], styles: StyleSheet1) -> list:
    """docs/clinical-safety.md §7: obligatorio en todo lugar donde se
    exporten `clinical_flags` — el checklist que las genera no está
    validado clínicamente, con independencia de que el artefacto esté
    aprobado."""
    flowables = [
        Paragraph(f"<i>{escape(RULESET_DISCLAIMER)}</i>", styles["Normal"]),
        Spacer(1, _ITEM_SPACING),
    ]
    flags = content.get("flags") or []
    if not flags:
        flowables.append(Paragraph(EMPTY_VALUE_PLACEHOLDER, styles["Normal"]))
        return flowables
    for flag in flags:
        line = f"[{flag['category']}] {flag['description']} ({flag['ruleset_name']})"
        flowables.append(Paragraph(escape(line), styles["Normal"]))
    return flowables


def _render_missing_information(content: dict[str, Any], styles: StyleSheet1) -> list:
    items = content.get("items") or []
    if not items:
        return [Paragraph(EMPTY_VALUE_PLACEHOLDER, styles["Normal"])]
    flowables = []
    for item in items:
        flowables.append(Paragraph(f"<b>Tema:</b> {escape(item['topic'])}", styles["Normal"]))
        flowables.append(
            Paragraph(
                f"<b>Pregunta sugerida:</b> {escape(item['suggested_question'])}",
                styles["Normal"],
            )
        )
        flowables.append(Spacer(1, _ITEM_SPACING))
    return flowables


def _render_anamnesis(content: dict[str, Any], styles: StyleSheet1) -> list:
    flowables = []
    for field_name in ANAMNESIS_FIELDS:
        field = content.get(field_name)
        if field is None:
            continue
        value = field.get("value") or EMPTY_VALUE_PLACEHOLDER
        heading = f"{humanize_field_name(field_name)} [{field['status']}]"
        flowables.append(Paragraph(escape(heading), styles["Heading3"]))
        flowables.append(Paragraph(escape(value), styles["Normal"]))
        flowables.append(Spacer(1, _ITEM_SPACING))
    return flowables


def _render_session_notes(content: dict[str, Any], styles: StyleSheet1) -> list:
    flowables = []
    for block_name in SESSION_NOTES_BLOCKS:
        block = content.get(block_name)
        if block is None:
            continue
        text = block.get("text") or UNEXPLORED_BLOCK_PLACEHOLDER
        flowables.append(Paragraph(escape(humanize_field_name(block_name)), styles["Heading3"]))
        flowables.append(Paragraph(escape(text), styles["Normal"]))
        flowables.append(Spacer(1, _ITEM_SPACING))
    return flowables


_BODY_RENDERERS: dict[AIArtifactType, Callable[[dict[str, Any], StyleSheet1], list]] = {
    AIArtifactType.TRANSCRIPT: _render_transcript,
    AIArtifactType.SUMMARY: _render_prose,
    AIArtifactType.PATIENT_SUMMARY: _render_prose,
    AIArtifactType.CLINICAL_FLAGS: _render_clinical_flags,
    AIArtifactType.MISSING_INFORMATION: _render_missing_information,
    AIArtifactType.ANAMNESIS: _render_anamnesis,
    AIArtifactType.SESSION_NOTES: _render_session_notes,
}


class PdfDocumentExporter:
    """Implementación en PDF de `DocumentExporter` (hito 6.6.1).
    Renderizado puro en memoria — sin E/S, sin async, sin ficheros
    temporales (ver el docstring de `DocumentExporter.export`)."""

    def export(self, document: ExportableDocument) -> bytes:
        renderer = _BODY_RENDERERS.get(document.artifact_type)
        if renderer is None:
            raise ValueError(
                f"PdfDocumentExporter no sabe renderizar artifact_type="
                f"{document.artifact_type!r}."
            )

        styles = getSampleStyleSheet()
        story: list = [
            Paragraph("Documento clínico exportado", styles["Title"]),
            Spacer(1, _SECTION_SPACING),
        ]
        for label, value in header_fields(document):
            story.append(Paragraph(f"<b>{label}:</b> {escape(value)}", styles["Normal"]))
        story.append(Spacer(1, _SECTION_SPACING * 2))
        story.append(Paragraph("Contenido", styles["Heading2"]))
        story.append(Spacer(1, _SECTION_SPACING))
        story.extend(renderer(document.content, styles))

        buffer = io.BytesIO()
        # `SimpleDocTemplate`/Platypus dividen automáticamente el `story`
        # en páginas según A4 cuando el contenido no cabe en una sola —
        # sin `PageBreak` manual, ver docs/fase-6-rfc.md (requisito 6.6.3
        # punto 6, "paginación automática").
        document_template = SimpleDocTemplate(buffer, pagesize=A4)
        document_template.build(story)
        return buffer.getvalue()
