"""Esquemas Pydantic de la API del AI Pipeline.

Ningún esquema de entrada admite campos gestionados por el servidor
(`status`, `confidence`, `provider_name`, timestamps, etc.) — con
`extra="forbid"` cualquier intento de enviarlos se rechaza con 422, mismo
criterio que `clinical_sessions/api/schemas.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai_pipeline.domain.entities import (
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersionSource,
    AIPipelineRunStatus,
)
from app.ai_pipeline.service import AIArtifactDetail, AIArtifactVersionDetail, PipelineRunOutcome
from app.core.messages.es import AI_DISCLAIMER

_REJECTION_REASON_MAX_LENGTH = 500


class ArtifactRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejection_reason: str | None = Field(default=None, max_length=_REJECTION_REASON_MAX_LENGTH)


class AIArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    clinical_session_id: uuid.UUID
    artifact_type: AIArtifactType
    status: AIArtifactStatus
    version_number: int | None
    content: dict[str, Any] | None
    confidence: int | None
    provider_name: str | None
    model_name: str | None
    schema_version: int
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    rejected_by: uuid.UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    ai_disclaimer: str = AI_DISCLAIMER

    @classmethod
    def from_detail(cls, detail: AIArtifactDetail) -> AIArtifactResponse:
        artifact = detail.artifact
        version = detail.current_version
        return cls(
            id=artifact.id,
            clinical_session_id=artifact.clinical_session_id,
            artifact_type=artifact.artifact_type,
            status=artifact.status,
            version_number=version.version_number if version else None,
            content=version.content if version else None,
            confidence=artifact.confidence,
            provider_name=detail.generation_run.provider_name if detail.generation_run else None,
            model_name=detail.generation_run.model_name if detail.generation_run else None,
            schema_version=artifact.schema_version,
            approved_by=artifact.approved_by,
            approved_at=artifact.approved_at,
            rejected_by=artifact.rejected_by,
            rejected_at=artifact.rejected_at,
            rejection_reason=artifact.rejection_reason,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )


class AIArtifactListResponse(BaseModel):
    items: list[AIArtifactResponse]


class AIArtifactVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    version_number: int
    content: dict[str, Any]
    confidence: int | None
    source: AIArtifactVersionSource
    provider_name: str | None
    model_name: str | None
    is_current: bool
    created_at: datetime

    @classmethod
    def from_detail(cls, detail: AIArtifactVersionDetail) -> AIArtifactVersionResponse:
        version = detail.version
        return cls(
            id=version.id,
            version_number=version.version_number,
            content=version.content,
            confidence=version.confidence,
            source=version.source,
            provider_name=detail.generation_run.provider_name if detail.generation_run else None,
            model_name=detail.generation_run.model_name if detail.generation_run else None,
            is_current=detail.is_current,
            created_at=version.created_at,
        )


class AIArtifactVersionListResponse(BaseModel):
    items: list[AIArtifactVersionResponse]


class PipelineStepOutcomeResponse(BaseModel):
    artifact_type: AIArtifactType
    status: str
    failure_reason: str | None
    skipped_reason: str | None
    latency_ms: int | None
    execution_time_ms: int | None
    input_token_count: int | None
    output_token_count: int | None
    estimated_cost_usd: Decimal | None


class RunMockPipelineResponse(BaseModel):
    pipeline_run_id: uuid.UUID
    status: AIPipelineRunStatus
    started_at: datetime
    completed_at: datetime | None
    artifacts: list[AIArtifactResponse]
    step_outcomes: list[PipelineStepOutcomeResponse]

    @classmethod
    def from_outcome(cls, outcome: PipelineRunOutcome) -> RunMockPipelineResponse:
        return cls(
            pipeline_run_id=outcome.pipeline_run.id,
            status=outcome.pipeline_run.status,
            started_at=outcome.pipeline_run.started_at,
            completed_at=outcome.pipeline_run.completed_at,
            artifacts=[AIArtifactResponse.from_detail(detail) for detail in outcome.artifacts],
            step_outcomes=[
                PipelineStepOutcomeResponse(
                    artifact_type=step.artifact_type,
                    status=(step.status.value if step.status is not None else "skipped"),
                    failure_reason=step.failure_reason,
                    skipped_reason=step.skipped_reason,
                    latency_ms=step.latency_ms,
                    execution_time_ms=step.execution_time_ms,
                    input_token_count=step.input_token_count,
                    output_token_count=step.output_token_count,
                    estimated_cost_usd=step.estimated_cost_usd,
                )
                for step in outcome.outcomes
            ],
        )
