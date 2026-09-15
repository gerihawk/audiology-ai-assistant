"""Endpoints de invitaciones (Fase 12, hito 12.2).

`POST /clinics/{clinic_id}/invitations`: autenticado, solo `admin` de esa
misma clínica (`authorize_invitation_action`, ver
app/core/authorization.py). Sin límite de rate limiting propio: a
diferencia de las superficies públicas del hito 12.1, esta ya exige un
JWT/X-Dev-User-Id válido — el límite general de la app (120/minute, ver
app/core/rate_limit.py) es suficiente, mismo criterio que el resto de
endpoints autenticados del proyecto. Responde 202 (no 201): la creación de
la invitación es condicional (no-enumeración, ver
`InvitationService.create_invitation`) — el cliente nunca puede distinguir
por la respuesta si se creó una invitación real o no.

`POST /invitations/{token}/accept`: público, sin autenticación previa —
mismo riesgo de abuso que `/auth/login`/onboarding hito 12.1, con el mismo
límite de 5/minute (ver docs/fase-12-rfc.md §5).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status

from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_invitation_service
from app.core.rate_limit import limiter
from app.onboarding.api.invitation_schemas import InvitationAcceptRequest, InvitationCreateRequest
from app.onboarding.invitation_service import InvitationAcceptData, InvitationService
from app.users.domain.entities import Role

router = APIRouter(tags=["invitations"])


@router.post("/clinics/{clinic_id}/invitations", status_code=status.HTTP_202_ACCEPTED)
async def create_invitation(
    clinic_id: uuid.UUID,
    payload: InvitationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: InvitationService = Depends(get_invitation_service),
) -> None:
    await service.create_invitation(current_user, clinic_id, payload.email, Role(payload.role))


@router.post("/invitations/{token}/accept", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def accept_invitation(
    token: str,
    payload: InvitationAcceptRequest,
    request: Request,
    service: InvitationService = Depends(get_invitation_service),
) -> None:
    await service.accept_invitation(
        InvitationAcceptData(
            token=token,
            new_password=payload.new_password,
            display_name=payload.display_name,
        )
    )
