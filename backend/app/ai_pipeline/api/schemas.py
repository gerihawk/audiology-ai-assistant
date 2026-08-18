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
    ruleset_disclaimer_for,
)
from app.ai_pipeline.service import (
    AIArtifactDetail,
    AIArtifactVersionDetail,
    AnamnesisUpdateProposalOutcome,
    PipelineRunOutcome,
)
from app.core.messages.es import AI_DISCLAIMER

_REJECTION_REASON_MAX_LENGTH = 500


class ArtifactRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejection_reason: str | None = Field(default=None, max_length=_REJECTION_REASON_MAX_LENGTH)


_CHANGE_NOTE_MAX_LENGTH = 2000


class ArtifactEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]
    change_note: str | None = Field(default=None, max_length=_CHANGE_NOTE_MAX_LENGTH)


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
    #: docs/clinical-safety.md §7 — decisión de qué `artifact_type` lo
    #: lleva vive en `ruleset_disclaimer_for()`
    #: (`ai_pipeline/domain/entities.py`), única fuente de verdad
    #: compartida con `ClinicalRecordDocumentResponse`. Este schema solo
    #: serializa el resultado.
    ruleset_disclaimer: str | None = None

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
            ruleset_disclaimer=ruleset_disclaimer_for(artifact.artifact_type),
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


class AnamnesisUpdateProposalResponse(BaseModel):
    """Respuesta de `POST .../propose-anamnesis-update` (Hito 6.5.3).

    Distingue explícitamente dos resultados válidos (RFC técnico de 6.5
    §15 del encargo de 6.5.3): `created=True` (propuesta persistida,
    `artifact_id`/`version_number`/`status` presentes) y `created=False`
    ("no changes proposed" — el generador no encontró nada que
    actualizar, sin `artifact_id` porque no se persistió nada). Nunca
    devuelve `content` clínico completo — solo qué campos cambiaron, no
    los valores (esos se consultan vía `GET /ai-artifacts/{id}` una vez
    creada la propuesta)."""

    model_config = ConfigDict(extra="forbid")

    created: bool
    artifact_id: uuid.UUID | None
    version_number: int | None
    status: AIArtifactStatus | None
    changed_fields: list[str]
    ai_disclaimer: str = AI_DISCLAIMER

    @classmethod
    def from_outcome(
        cls, outcome: AnamnesisUpdateProposalOutcome
    ) -> AnamnesisUpdateProposalResponse:
        if outcome.detail is None:
            return cls(
                created=False,
                artifact_id=None,
                version_number=None,
                status=None,
                changed_fields=[],
            )
        artifact = outcome.detail.artifact
        version = outcome.detail.current_version
        return cls(
            created=True,
            artifact_id=artifact.id,
            version_number=version.version_number if version else None,
            status=artifact.status,
            changed_fields=outcome.changed_fields,
        )


class RunPipelineResponse(BaseModel):
    """Forma de respuesta compartida por los dos entrypoints del pipeline
    (`run-pipeline` configurado y `run-mock-pipeline` — ver
    docs/fase-6-rfc.md, corrección de frontera mock/real): idéntica en
    ambos casos, la diferencia está en qué `PipelineStep` se ejecutaron,
    nunca en la forma de la respuesta."""

    pipeline_run_id: uuid.UUID
    status: AIPipelineRunStatus
    started_at: datetime
    completed_at: datetime | None
    artifacts: list[AIArtifactResponse]
    step_outcomes: list[PipelineStepOutcomeResponse]

    @classmethod
    def from_outcome(cls, outcome: PipelineRunOutcome) -> RunPipelineResponse:
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
