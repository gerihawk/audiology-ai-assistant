"""Puerto `DocumentExporter` — RFC §7.1: contrato único, sin nombre
competidor `ClinicalRecordExporter`. `PdfDocumentExporter`/
`TextDocumentExporter` (hito 6.6.2) lo implementan.

Sin BD, sin HTTP: transforma un `ExportableDocument` ya construido en los
bytes del documento de salida. Ninguna implementación consulta
repositorios directamente ni genera `AIArtifact` — el DTO ya trae todo lo
necesario (RFC §7.1).
"""

from __future__ import annotations

from typing import Protocol

from app.export.domain.entities import ExportableDocument


class DocumentExporter(Protocol):
    def export(self, document: ExportableDocument) -> bytes:
        """Renderizado puro en memoria. Deliberadamente síncrono: a
        diferencia de `SummaryGenerator`/`TranscriptionProvider` (que
        llaman a un proveedor externo real), aquí no hay ninguna E/S que
        justifique `async` — el DTO ya está completamente resuelto."""
        ...
