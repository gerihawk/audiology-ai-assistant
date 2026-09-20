"""Dependencias FastAPI: sesión de BD, usuario actual, servicios."""

from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.service import AIPipelineService
from app.audio.service import AudioRecordingService
from app.auth.service import AuthService
from app.billing.service import BillingService
from app.clinical_record.service import ClinicalRecordService
from app.clinical_sessions.service import ClinicalSessionService
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.consents.service import ConsentService
from app.core.config import get_settings
from app.core.context import get_request_id
from app.core.current_user import (
    CurrentUser,
    CurrentUserProvider,
    FakeCurrentUserProvider,
    RealCurrentUserProvider,
)
from app.core.db import get_db_session
from app.core.exceptions import ForbiddenError
from app.core.sentry import tag_current_user
from app.export.service import ExportService
from app.integrations.domain.email_sender import EmailSender
from app.integrations.domain.payment_gateway import PaymentGateway
from app.integrations.domain.transcription_provider import TranscriptionProvider
from app.integrations.domain.turnstile_verifier import TurnstileVerifier
from app.integrations.factory import (
    build_email_sender,
    build_payment_gateway,
    build_transcription_provider,
    build_turnstile_verifier,
)
from app.integrations.service import IntegrationConfigService
from app.onboarding.invitation_service import InvitationService
from app.onboarding.service import OnboardingService
from app.patients.service import PatientService
from app.retention.service import RetentionCleanupService

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
    "get_configured_email_sender",
    "get_configured_turnstile_verifier",
    "get_export_service",
    "get_clinical_record_service",
    "get_consent_service",
    "get_retention_cleanup_service",
    "get_integration_config_service",
    "get_auth_service",
    "get_onboarding_service",
    "get_invitation_service",
    "get_configured_payment_gateway",
    "get_billing_service",
    "require_active_subscription",
]


@lru_cache
def get_current_user_provider() -> CurrentUserProvider:
    """Según `settings.auth_mode` (Fase 9, hito 9.1): "fake" (por
    defecto, sin cambios) resuelve `FakeCurrentUserProvider`
    (X-Dev-User-Id); "real" resuelve `RealCurrentUserProvider` (JWT
    Bearer). Se cachea: la validación de producción de
    FakeCurrentUserProvider ocurre una única vez, en la primera
    invocación (idealmente en el arranque de la app, ver app.main
    lifespan)."""
    settings = get_settings()
    if settings.auth_mode == "real":
        return RealCurrentUserProvider(settings)
    return FakeCurrentUserProvider(settings)


@lru_cache
def get_configured_transcription_provider() -> TranscriptionProvider:
    """Resuelve `TranscriptionProvider` según `TRANSCRIPTION_PROVIDER` — ver
    app/integrations/factory.py. Se cachea: si la configuración es
    inválida (p. ej. `assemblyai` sin API key), falla una única vez, en
    el arranque (ver app.main lifespan), no en cada petición."""
    return build_transcription_provider(get_settings())


@lru_cache
def get_configured_email_sender() -> EmailSender:
    """Resuelve `EmailSender` según `EMAIL_PROVIDER` — ver
    app/integrations/factory.py. Se cachea, mismo criterio que
    `get_configured_transcription_provider`: si la configuración es
    inválida (p. ej. `brevo` sin API key), falla una única vez, en el
    arranque (ver app.main lifespan), no en cada petición."""
    return build_email_sender(get_settings())


@lru_cache
def get_configured_turnstile_verifier() -> TurnstileVerifier:
    """Resuelve `TurnstileVerifier` según `TURNSTILE_PROVIDER` — ver
    app/integrations/factory.py. Se cachea, mismo criterio que
    `get_configured_email_sender`: si la configuración es inválida (p. ej.
    `cloudflare` sin TURNSTILE_SECRET_KEY), falla una única vez, en el
    arranque (ver app.main lifespan), no en cada petición."""
    return build_turnstile_verifier(get_settings())


@lru_cache
def get_configured_payment_gateway() -> PaymentGateway:
    """Resuelve `PaymentGateway` según `PAYMENT_GATEWAY` — ver
    app/integrations/factory.py. Se cachea, mismo criterio que
    `get_configured_email_sender`: si la configuración es inválida (p. ej.
    `stripe` sin `STRIPE_SECRET_KEY`), falla una única vez, en el arranque
    (ver app.main lifespan), no en cada petición."""
    return build_payment_gateway(get_settings())


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    provider: CurrentUserProvider = Depends(get_current_user_provider),
) -> CurrentUser:
    current_user = await provider.get_current_user(request, session)
    await _ensure_clinic_is_active(session, current_user.clinic_id)
    # Solo `.id` (UUID opaco) — nunca `.email`/`.display_name`, aunque
    # `CurrentUser` los exponga a los dos (ver core/current_user.py).
    tag_current_user(current_user.id)
    return current_user


async def _ensure_clinic_is_active(session: AsyncSession, clinic_id: uuid.UUID) -> None:
    """Fase 14 — gate de acceso por `Clinic.is_active` (panel de gestión
    de clínicas del operador de la plataforma, `app.platform_admin`).
    Antes de esta fase, `is_active` existía en la tabla pero no bloqueaba
    nada (ver `SqlAlchemyClinicRepository.list_unverified_older_than`,
    único uso previo, que comprueba usuarios activos, no la propia
    clínica). Centralizado aquí (no en cada `authorize_*`): así se aplica
    a TODA la superficie autenticada de la app de una sola vez, igual que
    ya hace la comprobación de `user.is_active` dentro de cada
    `CurrentUserProvider`. Es una consulta extra por petición autenticada
    — coste aceptado a cambio de un único punto de verdad; si en el
    futuro pesa, se puede fusionar con la consulta de `User` mediante un
    join, pero no antes de que haga falta.

    `ForbiddenError` (403), no `UnauthenticatedError` (401): las
    credenciales del usuario siguen siendo válidas, lo que falta es
    autorización para operar mientras su clínica esté desactivada — igual
    que ya distingue el resto de `authorize_*` en app/core/authorization.py.
    Si la clínica no existiera (no debería pasar nunca: `clinic_id` es una
    FK NOT NULL), se trata igual que desactivada, nunca se deja pasar."""
    clinic = await SqlAlchemyClinicRepository().get_by_id(session, clinic_id)
    if clinic is None or not clinic.is_active:
        raise ForbiddenError(
            "Esta clínica está desactivada. Contacta con el soporte de la plataforma."
        )


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


async def get_retention_cleanup_service(
    session: AsyncSession = Depends(get_db_session),
) -> RetentionCleanupService:
    return RetentionCleanupService(session)


async def get_integration_config_service(
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationConfigService:
    return IntegrationConfigService(session)


async def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuthService:
    return AuthService(session)


async def get_onboarding_service(
    session: AsyncSession = Depends(get_db_session),
) -> OnboardingService:
    return OnboardingService(session)


async def get_invitation_service(
    session: AsyncSession = Depends(get_db_session),
) -> InvitationService:
    return InvitationService(session)


async def get_billing_service(
    session: AsyncSession = Depends(get_db_session),
    configured_payment_gateway: PaymentGateway = Depends(get_configured_payment_gateway),
) -> BillingService:
    return BillingService(session, payment_gateway=configured_payment_gateway)


async def require_active_subscription(
    current_user: CurrentUser = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
) -> None:
    """Fase 13, hito 13.2 — gate de acceso por `subscription_status`
    (docs/fase-13-rfc.md §5). Dependencia FastAPI, no una comprobación
    dentro de un servicio: se aplica SOLO en la ruta
    `POST .../run-pipeline` (ver app/ai_pipeline/api/router.py), nunca en
    `run-mock-pipeline` ni en el resto de endpoints de negocio — alcance
    deliberadamente acotado a la única operación que gasta dinero real,
    ver `BillingService.check_active_subscription`."""
    await billing_service.check_active_subscription(current_user)
