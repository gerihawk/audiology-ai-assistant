"""Endpoints /api/v1/patients/{patient_id}/consents — Fase 7.1."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.consents.api.schemas import ConsentCreateRequest, ConsentListResponse, ConsentResponse
from app.consents.service import ConsentCreateData, ConsentService
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_consent_service, get_current_user

router = APIRouter(prefix="/patients/{patient_id}/consents", tags=["consents"])


@router.post("", response_model=ConsentResponse, status_code=201)
async def create_consent(
    patient_id: uuid.UUID,
    payload: ConsentCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
    request_id: str = Depends(get_request_id),
) -> ConsentResponse:
    consent = await service.create(
        current_user,
        patient_id,
        ConsentCreateData(
            consent_type=payload.consent_type,
            granted=payload.granted,
            notes=payload.notes,
        ),
        request_id,
    )
    return ConsentResponse.model_validate(consent)


@router.get("", response_model=ConsentListResponse)
async def list_consents(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
) -> ConsentListResponse:
    items = await service.list_by_patient(current_user, patient_id)
    return ConsentListResponse(items=[ConsentResponse.model_validate(item) for item in items])
