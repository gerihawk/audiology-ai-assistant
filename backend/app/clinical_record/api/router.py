"""Endpoints de la historia clínica longitudinal — Hito 6.7.4
(docs/fase-6-rfc.md §7.2/§7.5, scope=patient; scope=session sigue siendo
competencia de `export`, hito 6.6.4).

Sin lógica de presentación en el router: `GET .../clinical-record`
delega en `ClinicalRecordPageResponse.from_page` y `GET
.../clinical-record/export` traduce el `ClinicalRecordExportResult` de
`ClinicalRecordService` a una `Response` HTTP en memoria — nunca
`StreamingResponse`/`FileResponse`, mismo criterio que
`export/api/router.py`: `export_record()` ya devuelve `bytes` completos
en memoria.

`format: ExportFormat` (`Literal["pdf", "text"]`) hace que FastAPI valide
el query param de forma nativa: un valor desconocido produce `422` sin
código de validación propio.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response

from app.clinical_record.api.schemas import ClinicalRecordPageResponse
from app.clinical_record.service import ClinicalRecordService, ExportFormat
from app.core.config import Settings, get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_clinical_record_service, get_current_user

router = APIRouter(prefix="/patients/{patient_id}/clinical-record", tags=["clinical-record"])


@router.get("", response_model=ClinicalRecordPageResponse)
async def get_clinical_record(
    patient_id: uuid.UUID,
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalRecordService = Depends(get_clinical_record_service),
    request_id: str = Depends(get_request_id),
    settings: Settings = Depends(get_settings),
) -> ClinicalRecordPageResponse:
    effective_limit = min(limit, settings.pagination_max_limit)
    page = await service.get_record(
        current_user,
        patient_id,
        limit=effective_limit,
        offset=offset,
        request_id=request_id,
    )
    return ClinicalRecordPageResponse.from_page(page)


@router.get("/export")
async def export_clinical_record(
    patient_id: uuid.UUID,
    format: ExportFormat,
    limit: int | None = Query(default=None, gt=0),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalRecordService = Depends(get_clinical_record_service),
    request_id: str = Depends(get_request_id),
) -> Response:
    result = await service.export_record(
        current_user,
        patient_id,
        export_format=format,
        limit=limit,
        offset=offset,
        request_id=request_id,
    )
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
