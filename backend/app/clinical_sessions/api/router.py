"""Endpoints /api/v1/clinical-sessions."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.clinical_sessions.api.schemas import (
    ClinicalSessionCreateRequest,
    ClinicalSessionListResponse,
    ClinicalSessionResponse,
    ClinicalSessionUpdateRequest,
    update_payload_from_request,
)
from app.clinical_sessions.domain.entities import ClinicalSessionStatus, SessionType
from app.clinical_sessions.service import (
    ClinicalSessionCreateData,
    ClinicalSessionService,
    ClinicalSessionUpdateData,
)
from app.core.config import Settings, get_settings
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_clinical_session_service, get_current_user

router = APIRouter(prefix="/clinical-sessions", tags=["clinical-sessions"])


@router.post("", response_model=ClinicalSessionResponse, status_code=201)
async def create_clinical_session(
    payload: ClinicalSessionCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.create(
        current_user,
        ClinicalSessionCreateData(
            patient_id=payload.patient_id,
            professional_id=payload.professional_id,
            session_type=payload.session_type,
            status=ClinicalSessionStatus(payload.status),
            scheduled_at=payload.scheduled_at,
            title=payload.title,
            administrative_notes=payload.administrative_notes,
        ),
        request_id,
    )
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.get("", response_model=ClinicalSessionListResponse)
async def list_clinical_sessions(
    patient_id: uuid.UUID | None = Query(default=None),
    professional_id: uuid.UUID | None = Query(default=None),
    status: ClinicalSessionStatus | None = Query(default=None),
    session_type: SessionType | None = Query(default=None),
    scheduled_from: date | None = Query(default=None),
    scheduled_to: date | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    settings: Settings = Depends(get_settings),
) -> ClinicalSessionListResponse:
    effective_limit = min(limit, settings.pagination_max_limit)
    items, total = await service.list(
        current_user,
        patient_id=patient_id,
        professional_id=professional_id,
        status=status,
        session_type=session_type,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        search=search,
        include_archived=include_archived,
        limit=effective_limit,
        offset=offset,
    )
    return ClinicalSessionListResponse(
        items=[ClinicalSessionResponse.model_validate(item) for item in items],
        total=total,
        limit=effective_limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=ClinicalSessionResponse)
async def get_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
) -> ClinicalSessionResponse:
    clinical_session = await service.get(current_user, session_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.patch("/{session_id}", response_model=ClinicalSessionResponse)
async def update_clinical_session(
    session_id: uuid.UUID,
    payload: ClinicalSessionUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.update(
        current_user,
        session_id,
        ClinicalSessionUpdateData(provided=update_payload_from_request(payload)),
        request_id,
    )
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/start", response_model=ClinicalSessionResponse)
async def start_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.start(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/complete", response_model=ClinicalSessionResponse)
async def complete_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.complete(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/submit-review", response_model=ClinicalSessionResponse)
async def submit_review_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.submit_review(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/review", response_model=ClinicalSessionResponse)
async def review_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.review(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/cancel", response_model=ClinicalSessionResponse)
async def cancel_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.cancel(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/archive", response_model=ClinicalSessionResponse)
async def archive_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.archive(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)


@router.post("/{session_id}/restore", response_model=ClinicalSessionResponse)
async def restore_clinical_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ClinicalSessionService = Depends(get_clinical_session_service),
    request_id: str = Depends(get_request_id),
) -> ClinicalSessionResponse:
    clinical_session = await service.restore(current_user, session_id, request_id)
    return ClinicalSessionResponse.model_validate(clinical_session)
