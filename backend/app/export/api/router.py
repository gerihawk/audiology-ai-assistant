"""Endpoint de exportación individual de documentos clínicos — Hito 6.6.4
(docs/fase-6-rfc.md §7.2/§7.5, scope=session únicamente; scope=patient es
competencia de `clinical_record`, hito 6.7).

Sin lógica de presentación aquí: el router solo traduce el `ExportResult`
de `ExportService` a una `Response` HTTP en memoria — nunca
`StreamingResponse`/`FileResponse`. No hay fichero ni stream real que lo
justifique: `ExportService.export()` ya devuelve `bytes` completos en
memoria (ver `export/infrastructure/pdf_exporter.py`/`text_exporter.py`,
ambos `io.BytesIO()` puro, sin tempfile).

`format: ExportFormat` (`Literal["pdf", "text"]`, ver `export/service.py`)
hace que FastAPI valide el query param de forma nativa: un valor
desconocido produce `422` sin código de validación propio.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response

from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_export_service
from app.export.service import ExportFormat, ExportService

router = APIRouter(tags=["export"])


@router.get("/ai-artifacts/{artifact_id}/export")
async def export_ai_artifact(
    artifact_id: uuid.UUID,
    format: ExportFormat,
    current_user: CurrentUser = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
    request_id: str = Depends(get_request_id),
) -> Response:
    result = await service.export(current_user, artifact_id, format, request_id)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
