"""Endpoints del AI Pipeline (Fase 4.1 + historial de versiones + Fase 5).

Sin prefijo común: combina rutas bajo `/clinical-sessions/{id}/...`,
`/ai-artifacts/{id}` y `/audio-recordings/{id}/transcribe` — ver
docs/development-plan.md Fase 4.6. `POST .../transcribe` vive aquí y no en
`audio/api/router.py` porque su responsabilidad es producir un
`AIArtifact` (transcript) a partir de un audio ya subido, con el
`TranscriptionProvider` resuelto por configuración — ver
docs/transcription-benchmark.md.

**Dos entrypoints de disparo del pipeline** (corrección de frontera
mock/real, Fase 6.3 — ver docs/fase-6-rfc.md): `run-mock-pipeline` es
Mock, determinista y estructuralmente incapaz de gastar dinero o enviar
datos a un tercero, pase lo que pase en `Settings`
(`AIPipelineService.run_mock_pipeline`/`_build_mock_steps`, que nunca
consulta el routing). `run-pipeline` respeta el routing real por
artifact_type (`Settings.llm_provider_*`) y puede invocar
Anthropic/OpenAI/Google si así está configurado."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.ai_pipeline.api.schemas import (
    AIArtifactListResponse,
    AIArtifactResponse,
    AIArtifactVersionListResponse,
    AIArtifactVersionResponse,
    AnamnesisUpdateProposalResponse,
    ArtifactEditRequest,
    ArtifactRejectRequest,
    RunPipelineResponse,
)
from app.ai_pipeline.service import AIPipelineService
from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_ai_pipeline_service, get_current_user

router = APIRouter(tags=["ai-pipeline"])


@router.post(
    "/clinical-sessions/{session_id}/run-mock-pipeline",
    response_model=RunPipelineResponse,
    status_code=201,
)
async def run_mock_pipeline(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> RunPipelineResponse:
    """Mock — cero LLM externo, nunca gasta dinero, sin importar cómo esté
    configurado `Settings` (ver `AIPipelineService.run_mock_pipeline`)."""
    outcome = await service.run_mock_pipeline(current_user, session_id, request_id)
    return RunPipelineResponse.from_outcome(outcome)


@router.post(
    "/clinical-sessions/{session_id}/run-pipeline",
    response_model=RunPipelineResponse,
    status_code=201,
)
async def run_pipeline(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> RunPipelineResponse:
    """Configurado — respeta el routing real por artifact_type; puede
    invocar Anthropic/OpenAI/Google y gastar dinero real si `Settings` lo
    indica (ver `AIPipelineService.run_pipeline`)."""
    outcome = await service.run_pipeline(current_user, session_id, request_id)
    return RunPipelineResponse.from_outcome(outcome)


@router.post(
    "/clinical-sessions/{session_id}/propose-anamnesis-update",
    response_model=AnamnesisUpdateProposalResponse,
    status_code=200,
)
async def propose_anamnesis_update(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> AnamnesisUpdateProposalResponse:
    """Acción EXPLÍCITA (RFC técnico de 6.5 §4 del encargo de 6.5.3) —
    nunca forma parte de `run-pipeline`/`run-mock-pipeline`, nunca se
    dispara automáticamente. `200` (no `201`): la operación puede
    completarse válidamente sin crear ningún recurso nuevo ("no changes
    proposed", ver `AnamnesisUpdateProposalResponse`)."""
    outcome = await service.propose_anamnesis_update(current_user, session_id, request_id)
    return AnamnesisUpdateProposalResponse.from_outcome(outcome)


@router.post("/audio-recordings/{audio_recording_id}/transcribe", response_model=AIArtifactResponse)
async def transcribe_audio_recording(
    audio_recording_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> AIArtifactResponse:
    detail = await service.transcribe_from_audio(current_user, audio_recording_id, request_id)
    return AIArtifactResponse.from_detail(detail)


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


@router.patch("/ai-artifacts/{artifact_id}/content", response_model=AIArtifactResponse)
async def edit_ai_artifact_content(
    artifact_id: uuid.UUID,
    payload: ArtifactEditRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> AIArtifactResponse:
    detail = await service.edit_content(
        current_user,
        artifact_id,
        request_id,
        content=payload.content,
        change_note=payload.change_note,
    )
    return AIArtifactResponse.from_detail(detail)


@router.delete("/ai-artifacts/{artifact_id}", status_code=204)
async def delete_ai_artifact(
    artifact_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AIPipelineService = Depends(get_ai_pipeline_service),
    request_id: str = Depends(get_request_id),
) -> None:
    await service.delete_artifact(current_user, artifact_id, request_id)
