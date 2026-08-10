"""Endpoints del AI Pipeline (Fase 4.1 + historial de versiones para el frontend).

Sin prefijo común: combina rutas bajo `/clinical-sessions/{id}/...` y
`/ai-artifacts/{id}` — ver docs/development-plan.md Fase 4.6. Además de
los 5 endpoints mínimos originales, `GET .../versions` (solo lectura,
necesario para que el frontend pueda navegar el historial de versiones —
sin él, "cambiar entre versiones" no tiene datos que mostrar).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.ai_pipeline.api.schemas import (
    AIArtifactListResponse,
    AIArtifactResponse,
    AIArtifactVersionListResponse,
    AIArtifactVersionResponse,
    ArtifactRejectRequest,
    RunMockPipelineResponse,
)
from app.ai_pipeline.service import AIPipelineService
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_ai_pipeline_service, get_current_user

router = APIRouter(tags=["ai-pipeline"])


@router.post(
    "/clinical-sessions/{session_id}/run-mock-pipeline",
    response_model=RunMockPipelineResponse,
    status_code=201,
)
async def run_mock_pipeline(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> RunMockPipelineResponse:
    outcome = await service.run_pipeline(current_user, session_id, request_id)
    return RunMockPipelineResponse.from_outcome(outcome)


@router.get("/clinical-sessions/{session_id}/artifacts", response_model=AIArtifactListResponse)
async def list_clinical_session_artifacts(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
) -> AIArtifactListResponse:
    details = await service.list_artifacts(current_user, session_id)
    return AIArtifactListResponse(
        items=[AIArtifactResponse.from_detail(detail) for detail in details]
    )


@router.get("/ai-artifacts/{artifact_id}", response_model=AIArtifactResponse)
async def get_ai_artifact(
    artifact_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
) -> AIArtifactResponse:
    detail = await service.get_artifact(current_user, artifact_id)
    return AIArtifactResponse.from_detail(detail)


@router.get("/ai-artifacts/{artifact_id}/versions", response_model=AIArtifactVersionListResponse)
async def list_ai_artifact_versions(
    artifact_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
) -> AIArtifactVersionListResponse:
    details = await service.list_versions(current_user, artifact_id)
    return AIArtifactVersionListResponse(
        items=[AIArtifactVersionResponse.from_detail(detail) for detail in details]
    )


@router.post("/ai-artifacts/{artifact_id}/approve", response_model=AIArtifactResponse)
async def approve_ai_artifact(
    artifact_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> AIArtifactResponse:
    detail = await service.approve(current_user, artifact_id, request_id)
    return AIArtifactResponse.from_detail(detail)


@router.post("/ai-artifacts/{artifact_id}/reject", response_model=AIArtifactResponse)
async def reject_ai_artifact(
    artifact_id: uuid.UUID,
    payload: ArtifactRejectRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> AIArtifactResponse:
    detail = await service.reject(
        current_user,
        artifact_id,
        request_id,
        rejection_reason=payload.rejection_reason if payload else None,
    )
    return AIArtifactResponse.from_detail(detail)
