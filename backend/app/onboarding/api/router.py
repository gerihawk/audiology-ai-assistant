"""Endpoints del onboarding self-service (Fase 12, hito 12.1) y limpieza
de clínicas fantasma (Fase 12, hito 12.4).

Los cuatro primeros son superficie pública, sin `Depends(get_current_user)`
— mismo patrón que `POST /auth/login`. Por el mismo motivo (superficie no
autenticada, mismo riesgo de fuerza bruta/abuso que login, ver
docs/fase-12-rfc.md §5) todos llevan el mismo límite propio de 5/minute que
`/auth/login`, más estricto que el general de la app (120/minute — ver
app/core/rate_limit.py). Decidido explícitamente el 2026-09-15: el RFC
había dejado el rate limiting dedicado para el hito 12.4, pero se adelanta
aquí para no dejar esta superficie sin proteger mientras tanto.

`POST /onboarding/system-cleanup`: NO depende de `get_current_user` —
mismo patrón que `POST /api/v1/retention/system-purge`
(app/retention/api/router.py): una acción de sistema cross-clínica
disparada por un cron externo, autenticada con la cabecera
`X-Onboarding-Cleanup-Cron-Secret` (ver `_verify_onboarding_cleanup_cron_secret`
y `Settings.onboarding_cleanup_cron_secret`). Reutiliza
`app.onboarding.cleanup_cli.main()` en vez de reimplementar el bootstrap.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.deps import get_onboarding_service
from app.core.rate_limit import limiter
from app.onboarding.api.schemas import (
    ClinicSignupRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    SystemCleanupResponse,
    VerifyEmailRequest,
)
from app.onboarding.cleanup_cli import main as run_system_cleanup
from app.onboarding.service import ClinicSignupData, OnboardingService

router = APIRouter(tags=["onboarding"])


@router.post("/clinics/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup_clinic(
    payload: ClinicSignupRequest,
    request: Request,
    service: OnboardingService = Depends(get_onboarding_service),
) -> None:
    await service.signup_clinic(
        ClinicSignupData(
            clinic_name=payload.clinic_name,
            admin_email=payload.admin_email,
            admin_display_name=payload.admin_display_name,
            admin_password=payload.admin_password,
        )
    )


@router.post("/onboarding/verify-email", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    service: OnboardingService = Depends(get_onboarding_service),
) -> None:
    await service.verify_email(payload.token)


@router.post("/onboarding/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def request_password_reset(
    payload: PasswordResetRequestRequest,
    request: Request,
    service: OnboardingService = Depends(get_onboarding_service),
) -> None:
    # Siempre 204, exista o no la cuenta (ver
    # OnboardingService.request_password_reset — no-enumeración).
    await service.request_password_reset(payload.email)


@router.post("/onboarding/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    service: OnboardingService = Depends(get_onboarding_service),
) -> None:
    await service.confirm_password_reset(payload.token, payload.new_password)


async def _verify_onboarding_cleanup_cron_secret(
    x_onboarding_cleanup_cron_secret: str | None = Header(
        default=None, alias="X-Onboarding-Cleanup-Cron-Secret"
    ),
) -> None:
    """Autentica al LLAMADOR del endpoint (un cron externo), no a un
    usuario — ver `Settings.onboarding_cleanup_cron_secret`.
    `secrets.compare_digest`, nunca `==`, para no filtrar el secreto por
    temporización — mismo criterio que
    `app.retention.api.router._verify_retention_cron_secret`."""
    expected = get_settings().onboarding_cleanup_cron_secret
    if x_onboarding_cleanup_cron_secret is None or not secrets.compare_digest(
        x_onboarding_cleanup_cron_secret, expected
    ):
        raise HTTPException(
            status_code=401, detail="X-Onboarding-Cleanup-Cron-Secret ausente o inválida."
        )


@router.post("/onboarding/system-cleanup", response_model=SystemCleanupResponse)
async def system_cleanup(
    _: None = Depends(_verify_onboarding_cleanup_cron_secret),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SystemCleanupResponse:
    result = await run_system_cleanup(session_factory)
    return SystemCleanupResponse(**result)
