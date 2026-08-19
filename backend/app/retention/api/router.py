"""Endpoints /api/v1/retention/expired-audio — Fase 7.2.

Reutiliza `AudioRecordingListResponse`/`AudioRecordingResponse` de
`app/audio/api/schemas.py`: la respuesta es una lista de grabaciones de
audio, sin forma propia que justifique duplicar el esquema.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.audio.api.schemas import AudioRecordingListResponse, AudioRecordingResponse
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_retention_cleanup_service
from app.retention.service import RetentionCleanupService

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/expired-audio", response_model=AudioRecordingListResponse)
async def list_expired_audio(
    current_user: CurrentUser = Depends(get_current_user),
    service: RetentionCleanupService = Depends(get_retention_cleanup_service),
) -> AudioRecordingListResponse:
    items = await service.find_expired_audio(current_user)
    return AudioRecordingListResponse(
        items=[AudioRecordingResponse.from_entity(item) for item in items]
    )


@router.post("/expired-audio/purge", response_model=AudioRecordingListResponse)
async def purge_expired_audio(
    current_user: CurrentUser = Depends(get_current_user),
    service: RetentionCleanupService = Depends(get_retention_cleanup_service),
    request_id: str = Depends(get_request_id),
) -> AudioRecordingListResponse:
    items = await service.purge(current_user, request_id)
    return AudioRecordingListResponse(
        items=[AudioRecordingResponse.from_entity(item) for item in items]
    )
