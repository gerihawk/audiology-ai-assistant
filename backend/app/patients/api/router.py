"""Endpoints /api/v1/patients."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_patient_service
from app.patients.api.schemas import (
    PatientCreateRequest,
    PatientListResponse,
    PatientResponse,
    PatientUpdateRequest,
    update_payload_from_request,
)
from app.patients.service import PatientCreateData, PatientService, PatientUpdateData

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientResponse, status_code=201)
async def create_patient(
    payload: PatientCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
    request_id: str = Depends(get_request_id),
) -> PatientResponse:
    patient = await service.create(
        current_user,
        PatientCreateData(
            internal_code=payload.internal_code,
            display_name=payload.display_name,
            birth_year=payload.birth_year,
            sex=payload.sex,
            preferred_language=payload.preferred_language,
            notes=payload.notes,
        ),
        request_id,
    )
    return PatientResponse.model_validate(patient)


@router.get("", response_model=PatientListResponse)
async def list_patients(
    search: str | None = Query(default=None, max_length=200),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
    settings: Settings = Depends(get_settings),
) -> PatientListResponse:
    effective_limit = min(limit, settings.pagination_max_limit)
    items, total = await service.list(
        current_user,
        search=search,
        include_archived=include_archived,
        limit=effective_limit,
        offset=offset,
    )
    return PatientListResponse(
        items=[PatientResponse.model_validate(item) for item in items],
        total=total,
        limit=effective_limit,
        offset=offset,
    )


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
) -> PatientResponse:
    patient = await service.get(current_user, patient_id)
    return PatientResponse.model_validate(patient)


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
    request_id: str = Depends(get_request_id),
) -> PatientResponse:
    patient = await service.update(
        current_user,
        patient_id,
        PatientUpdateData(provided=update_payload_from_request(payload)),
        request_id,
    )
    return PatientResponse.model_validate(patient)


@router.post("/{patient_id}/archive", response_model=PatientResponse)
async def archive_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
    request_id: str = Depends(get_request_id),
) -> PatientResponse:
    patient = await service.archive(current_user, patient_id, request_id)
    return PatientResponse.model_validate(patient)


@router.post("/{patient_id}/restore", response_model=PatientResponse)
async def restore_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: PatientService = Depends(get_patient_service),
    request_id: str = Depends(get_request_id),
) -> PatientResponse:
    patient = await service.restore(current_user, patient_id, request_id)
    return PatientResponse.model_validate(patient)
