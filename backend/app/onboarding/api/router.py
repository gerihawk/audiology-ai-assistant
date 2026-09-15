"""Endpoints del onboarding self-service (Fase 12, hito 12.1).

Los cuatro son superficie pública, sin `Depends(get_current_user)` — mismo
patrón que `POST /auth/login`. Por el mismo motivo (superficie no
autenticada, mismo riesgo de fuerza bruta/abuso que login, ver
docs/fase-12-rfc.md §5) todos llevan el mismo límite propio de 5/minute que
`/auth/login`, más estricto que el general de la app (120/minute — ver
app/core/rate_limit.py). Decidido explícitamente el 2026-09-15: el RFC
había dejado el rate limiting dedicado para el hito 12.4, pero se adelanta
aquí para no dejar esta superficie sin proteger mientras tanto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import get_onboarding_service
from app.core.rate_limit import limiter
from app.onboarding.api.schemas import (
    ClinicSignupRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    VerifyEmailRequest,
)
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
