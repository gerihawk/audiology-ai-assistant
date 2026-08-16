"""Helpers puros compartidos por `TextDocumentExporter`/`PdfDocumentExporter`
(hitos 6.6.2/6.6.3) — RFC §7.1, requisito 6.6.3 punto 9: ambos exportadores
deben mostrar exactamente los mismos campos, en el mismo orden, con la
misma resolución de "vacío"/"sin especificar", para no divergir en su
interpretación clínica del mismo `ExportableDocument`.

Deliberadamente NO incluye el layout del cuerpo por `artifact_type`: TXT y
PDF necesitan formas de página físicamente distintas (líneas planas vs.
flowables de Platypus, con estilos de encabezado en línea o en bloque
según el caso) y forzar una única función de renderizado de cuerpo
compartida sería la abstracción genérica de renderizado que la auditoría
de 6.6.3 pidió explícitamente evitar. Lo que sí es idéntico entre ambos —
constantes, humanización de nombres de campo y la cabecera de metadata —
vive aquí, una sola vez."""

from __future__ import annotations

from app.core.messages.es import RULESET_DISCLAIMER
from app.export.domain.entities import ExportableDocument

__all__ = [
    "UNSPECIFIED_SESSION_TYPE_LABEL",
    "EMPTY_VALUE_PLACEHOLDER",
    "UNEXPLORED_BLOCK_PLACEHOLDER",
    "RULESET_DISCLAIMER",
    "humanize_field_name",
    "header_fields",
]

UNSPECIFIED_SESSION_TYPE_LABEL = "Sin especificar"
EMPTY_VALUE_PLACEHOLDER = "(sin información)"
UNEXPLORED_BLOCK_PLACEHOLDER = "(no explorado)"


def humanize_field_name(field_name: str) -> str:
    """Transformación genérica, no un diccionario de etiquetas clínicas
    por campo (fuera de alcance de 6.6.2/6.6.3): `"motivo_consulta"` ->
    `"Motivo consulta"`. Suficiente para que ningún exportador emita el
    nombre de campo crudo sin inventar redacción clínica nueva."""
    return field_name.replace("_", " ").capitalize()


def header_fields(document: ExportableDocument) -> list[tuple[str, str]]:
    """RFC §7.4: clínica, paciente mínimo necesario, sesión, `session_type`
    (o "Sin especificar"), artefacto, versión, aprobación humana, fecha y
    hash de contenido — nunca provider/model/generation_run/coste
    (`ExportableDocument` no los transporta, ver hito 6.6.1). Devuelve
    pares (etiqueta, valor) ya resueltos a texto; cada exportador decide
    su propio layout físico (línea "Etiqueta: valor" en TXT, párrafo con
    etiqueta en negrita en PDF)."""
    patient = document.patient_internal_code
    if document.patient_display_name:
        patient = f"{patient} ({document.patient_display_name})"
    session_type = document.session_type or UNSPECIFIED_SESSION_TYPE_LABEL

    return [
        ("Clínica", document.clinic_name),
        ("Paciente", patient),
        ("Sesión", str(document.clinical_session_id)),
        ("Tipo de sesión", session_type),
        ("Tipo de documento", document.artifact_type.value),
        ("Versión", str(document.version_number)),
        ("Aprobado por", f"{document.approved_by} — {document.approved_at.isoformat()}"),
        ("Generado", document.generated_at.isoformat()),
        ("Hash de contenido (SHA-256)", document.content_hash),
    ]
