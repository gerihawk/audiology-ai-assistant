"""Entidades de dominio del AI Pipeline y sus enums. Sin dependencias de SQLAlchemy.

Ver docs/ai-pipeline-architecture.md §4 y docs/data-model.md §10 (diseño
cerrado). Dos ejes de estado independientes, nunca mezclados:
`AIGenerationRunStatus` (ejecución de un paso) y `AIArtifactStatus`
(disposición humana sobre el artefacto).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class AIArtifactType(StrEnum):
    TRANSCRIPT = "transcript"
    SUMMARY = "summary"
    CLINICAL_FLAGS = "clinical_flags"
    MISSING_INFORMATION = "missing_information"
    ANAMNESIS = "anamnesis"
    #: Contrato de dominio cerrado por docs/fase-6-rfc.md §4.3 (hito 6.2,
    #: precondición de arquitectura). Deliberadamente ausente de
    #: `PIPELINE_STEP_ORDER`: sin `PipelineStep`, sin entrada en el catálogo
    #: de `service.py`, nunca se genera en producción hasta el hito 6.3.
    PATIENT_SUMMARY = "patient_summary"


class AIArtifactStatus(StrEnum):
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AIArtifactVersionSource(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_EDITED = "human_edited"


class AIGenerationRunStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIPipelineRunStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_FAILED = "partially_failed"


#: Orden de ejecución de los pasos del pipeline en modo secuencial (una
#: ordenación topológica válida del grafo de dependencias — ver
#: docs/ai-pipeline-architecture.md §1.4). `PATIENT_SUMMARY` (Fase 6.3,
#: docs/fase-6-rfc.md §4.3) se inserta justo después de `SUMMARY`: su único
#: `depends_on()` formal es `TRANSCRIPT`, pero debe ejecutarse después de
#: `SUMMARY` para que `context.outputs` ya tenga su salida disponible como
#: enriquecimiento opcional — ver `PatientSummaryStep`.
PIPELINE_STEP_ORDER: tuple[AIArtifactType, ...] = (
    AIArtifactType.TRANSCRIPT,
    AIArtifactType.SUMMARY,
    AIArtifactType.PATIENT_SUMMARY,
    AIArtifactType.CLINICAL_FLAGS,
    AIArtifactType.MISSING_INFORMATION,
    AIArtifactType.ANAMNESIS,
)


@dataclass(slots=True)
class AIArtifact:
    id: uuid.UUID
    clinical_session_id: uuid.UUID
    artifact_type: AIArtifactType
    status: AIArtifactStatus
    current_version_id: uuid.UUID | None
    confidence: int | None
    schema_version: int
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    rejected_by: uuid.UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    deleted_by: uuid.UUID | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AIArtifactVersion:
    id: uuid.UUID
    ai_artifact_id: uuid.UUID
    version_number: int
    content: dict[str, Any]
    confidence: int | None
    source_map: dict[str, Any] | None
    source: AIArtifactVersionSource
    generation_run_id: uuid.UUID | None
    created_by: uuid.UUID | None
    change_note: str | None
    created_at: datetime


@dataclass(slots=True)
class AIGenerationRun:
    id: uuid.UUID
    ai_pipeline_run_id: uuid.UUID
    clinical_session_id: uuid.UUID
    artifact_type: AIArtifactType
    ai_artifact_id: uuid.UUID | None
    resulting_version_number: int | None
    status: AIGenerationRunStatus
    provider_name: str
    model_name: str | None
    prompt_template_id: uuid.UUID | None
    prompt_template_version: int | None
    input_token_count: int | None
    output_token_count: int | None
    estimated_cost_usd: Decimal | None
    latency_ms: int | None
    execution_time_ms: int | None
    rendered_system_prompt: str | None
    rendered_user_prompt: str | None
    raw_response: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None
    failure_reason: str | None
    request_id: str | None


@dataclass(slots=True)
class AIPipelineRun:
    id: uuid.UUID
    clinical_session_id: uuid.UUID
    triggered_by: uuid.UUID
    status: AIPipelineRunStatus
    started_at: datetime
    completed_at: datetime | None
    request_id: str | None


@dataclass(slots=True)
class PromptTemplate:
    id: uuid.UUID
    name: str
    version: int
    description: str | None
    system_prompt: str | None
    user_prompt_template: str
    variables_schema: dict[str, Any]
    is_active: bool
    created_by: uuid.UUID
    change_note: str | None
    created_at: datetime
    #: Añadidos en la Fase 6.0.5 (docs/development-plan.md) para permitir
    #: seleccionar la plantilla activa por artefacto e idioma sin depender
    #: de una convención de nombres. `variables_schema` declara las
    #: variables de esta plantilla como
    #: `{"required": [...], "optional": [...]}` — ver prompt_renderer.py.
    artifact_type: AIArtifactType
    language: str


@dataclass(slots=True, frozen=True)
class RenderContext:
    """Entrada de `PromptRenderer.render()` — variables tipadas (`str`) a
    sustituir en una `PromptTemplate` ya seleccionada. No decide qué
    plantilla usar (eso es responsabilidad del llamador vía
    `PromptTemplateRepository.get_active()`) ni conoce ningún proveedor
    LLM — ver docs/ai-pipeline-architecture.md §5 (tabla de
    responsabilidades)."""

    variables: dict[str, str]


@dataclass(slots=True, frozen=True)
class PromptRenderResult:
    """Salida de `PromptRenderer.render()`. Nunca se construye con un
    prompt incompleto: si faltara una variable obligatoria o sobrara una
    no declarada, `render()` lanza antes de llegar aquí."""

    system_prompt: str | None
    user_prompt: str
    variables_used: dict[str, str]
    template_id: uuid.UUID
    template_version: int
