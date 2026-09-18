"""Endpoints /api/v1/retention/* — Fase 7.2 (por-clínica), Fase 10.4
(purga de sistema cross-clínica, para el cron externo del entorno de
despliegue real) y la purga definitiva por paciente (añadida
2026-09-18, ver docs/privacy-and-security.md §8).

`/expired-audio`, `/expired-audio/purge`: reutilizan
`AudioRecordingListResponse`/`AudioRecordingResponse` de
`app/audio/api/schemas.py` — la respuesta es una lista de grabaciones de
audio, sin forma propia que justifique duplicar el esquema.

`/system-purge`: NO depende de `get_current_user` — no actúa como ningún
usuario de una clínica concreta, es una acción de sistema disparada por un
cron externo que autentica con la cabecera `X-Retention-Cron-Secret`
(ver `_verify_retention_cron_secret` y `Settings.retention_cron_secret`).
Reutiliza `app.retention.cli.main()` (mismo bucle cross-clínica que ya usa
el comando de CLI) en vez de reimplementarlo.

`/patients/{patient_id}/purge`: distinta de las dos anteriores — borra
físicamente TODO el contenido clínico (sesiones, artefactos de IA, audio)
de un paciente concreto, nunca solo audio expirado por antigüedad. Exige
`admin` (mismo criterio que el resto de `RetentionAction`) y un cuerpo
`{"confirm": true}` explícito — ver `PatientDataPurgeRequest`.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audio.api.schemas import AudioRecordingListResponse, AudioRecordingResponse
from app.core.config import get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.db import get_session_factory
from app.core.deps import get_current_user, get_retention_cleanup_service
from app.retention.api.schemas import (
    PatientDataPurgeRequest,
    PatientDataPurgeResponse,
    SystemPurgeResponse,
)
from app.retention.cli import main as run_system_purge
from app.retention.service import RetentionCleanupService

router = APIRouter(prefix="/retention", tags=["retention"])


async def _verify_retention_cron_secret(
    x_retention_cron_secret: str | None = Header(default=None, alias="X-Retention-Cron-Secret"),
) -> None:
    """Autentica al LLAMADOR del endpoint (un cron externo), no a un
    usuario — ver `Settings.retention_cron_secret`. `secrets.compare_digest`,
    nunca `==`, para no filtrar el secreto por temporización."""
    expected = get_settings().retention_cron_secret
    if x_retention_cron_secret is None or not secrets.compare_digest(
        x_retention_cron_secret, expected
    ):
        raise HTTPException(status_code=401, detail="X-Retention-Cron-Secret ausente o inválida.")


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


@router.post("/system-purge", response_model=SystemPurgeResponse)
async def system_purge(
    _: None = Depends(_verify_retention_cron_secret),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SystemPurgeResponse:
    result = await run_system_purge(session_factory)
    return SystemPurgeResponse(**result)


@router.post("/patients/{patient_id}/purge", response_model=PatientDataPurgeResponse)
async def purge_patient_clinical_data(
    patient_id: uuid.UUID,
    body: PatientDataPurgeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: RetentionCleanupService = Depends(get_retention_cleanup_service),
    request_id: str = Depends(get_request_id),
) -> PatientDataPurgeResponse:
    summary = await service.purge_patient_clinical_data(
        current_user, patient_id, request_id, confirm=body.confirm
    )
    return PatientDataPurgeResponse(
        clinical_sessions_purged=summary.clinical_sessions_purged,
        ai_artifacts_purged=summary.ai_artifacts_purged,
        audio_recordings_purged=summary.audio_recordings_purged,
    )
