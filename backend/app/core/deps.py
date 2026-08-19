"""Dependencias FastAPI: sesión de BD, usuario actual, servicios."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.service import AIPipelineService
from app.audio.service import AudioRecordingService
from app.clinical_record.service import ClinicalRecordService
from app.clinical_sessions.service import ClinicalSessionService
from app.consents.service import ConsentService
from app.core.config import get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser, CurrentUserProvider, FakeCurrentUserProvider
from app.core.db import get_db_session
from app.export.service import ExportService
from app.integrations.domain.transcription_provider import TranscriptionProvider
from app.integrations.factory import build_transcription_provider
from app.patients.service import PatientService

__all__ = [
    "get_db_session",
    "get_request_id",
    "get_current_user_provider",
    "get_current_user",
    "get_patient_service",
    "get_clinical_session_service",
    "get_ai_pipeline_service",
    "get_audio_recording_service",
    "get_configured_transcription_provider",
    "get_export_service",
    "get_clinical_record_service",
    "get_consent_service",
]


@lru_cache
def get_current_user_provider() -> CurrentUserProvider:
    """Se cachea: la validación de producción de FakeCurrentUserProvider
    ocurre una única vez, en la primera invocación (idealmente en el
    arranque de la app, ver app.main lifespan)."""
    return FakeCurrentUserProvider(get_settings())


@lru_cache
def get_configured_transcription_provider() -> TranscriptionProvider:
    """Resuelve `TranscriptionProvider` según `TRANSCRIPTION_PROVIDER` — ver
    app/integrations/factory.py. Se cachea: si la configuración es
    inválida (p. ej. `assemblyai` sin API key), falla una única vez, en
    el arranque (ver app.main lifespan), no en cada petición."""
    return build_transcription_provider(get_settings())


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    provider: CurrentUserProvider = Depends(get_current_user_provider),
) -> CurrentUser:
    return await provider.get_current_user(request, session)


async def get_patient_service(
    session: AsyncSession = Depends(get_db_session),
) -> PatientService:
    return PatientService(session)


async def get_clinical_session_service(
    session: AsyncSession = Depends(get_db_session),
) -> ClinicalSessionService:
    return ClinicalSessionService(session)


async def get_audio_recording_service(
    session: AsyncSession = Depends(get_db_session),
) -> AudioRecordingService:
    return AudioRecordingService(session)


async def get_ai_pipeline_service(
    session: AsyncSession = Depends(get_db_session),
    configured_transcription_provider: TranscriptionProvider = Depends(
        get_configured_transcription_provider
    ),
) -> AIPipelineService:
    return AIPipelineService(
        session, configured_transcription_provider=configured_transcription_provider
    )


async def get_export_service(
    session: AsyncSession = Depends(get_db_session),
) -> ExportService:
    return ExportService(session)


async def get_clinical_record_service(
    session: AsyncSession = Depends(get_db_session),
) -> ClinicalRecordService:
    return ClinicalRecordService(session)


async def get_consent_service(
    session: AsyncSession = Depends(get_db_session),
) -> ConsentService:
    return ConsentService(session)

