"""Endpoints de grabaciones de audio.

`POST .../transcribe` (Fase 5) vive en `ai_pipeline/api/router.py`, no
aquí: su responsabilidad es producir un `AIArtifact`, no gestionar el
audio en sí — mismo criterio que agrupa `/ai-artifacts/*` bajo
`ai_pipeline` en vez de bajo `clinical_sessions` (ver
app/ai_pipeline/api/router.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.audio.api.schemas import AudioRecordingListResponse, AudioRecordingResponse
from app.audio.service import AudioRecordingService, AudioUploadData
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_audio_recording_service, get_current_user

router = APIRouter(tags=["audio-recordings"])


@router.post(
    "/clinical-sessions/{session_id}/audio-recordings",
    response_model=AudioRecordingResponse,
    status_code=201,
)
async def upload_audio_recording(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    duration_seconds: int = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioRecordingService = Depends(get_audio_recording_service),
    request_id: str = Depends(get_request_id),
) -> AudioRecordingResponse:
    content = await file.read()
    audio_recording = await service.upload(
        current_user,
        session_id,
        AudioUploadData(
            original_filename=file.filename or "audio",
            mime_type=file.content_type or "application/octet-stream",
            content=content,
            duration_seconds=duration_seconds,
        ),
        request_id,
    )
    return AudioRecordingResponse.from_entity(audio_recording)


@router.get(
    "/clinical-sessions/{session_id}/audio-recordings", response_model=AudioRecordingListResponse
)
async def list_audio_recordings(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioRecordingService = Depends(get_audio_recording_service),
) -> AudioRecordingListResponse:
    items = await service.list_for_session(current_user, session_id)
    return AudioRecordingListResponse(
        items=[AudioRecordingResponse.from_entity(item) for item in items]
    )


@router.delete("/audio-recordings/{audio_recording_id}", response_model=AudioRecordingResponse)
async def delete_audio_recording(
    audio_recording_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioRecordingService = Depends(get_audio_recording_service),
    request_id: str = Depends(get_request_id),
) -> AudioRecordingResponse:
    audio_recording = await service.delete(current_user, audio_recording_id, request_id)
    return AudioRecordingResponse.from_entity(audio_recording)
