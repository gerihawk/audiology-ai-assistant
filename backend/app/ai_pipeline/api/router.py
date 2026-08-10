"""Endpoints mínimos del AI Pipeline (Fase 4.1).

Sin prefijo común: combina rutas bajo `/clinical-sessions/{id}/...` y
`/ai-artifacts/{id}` — ver docs/development-plan.md Fase 4.6. Solo los 5
endpoints pedidos, ninguno adicional (sin edición, sin listado de
versiones, sin detalle de ejecución — quedan para una ronda posterior).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.ai_pipeline.api.schemas import (
    AIArtifactListResponse,
    AIArtifactResponse,
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
