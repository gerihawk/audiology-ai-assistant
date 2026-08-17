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
    #: Contrato cerrado por docs/fase-6-rfc.md §4.7 (hito 6.4.3, RFC
    #: técnico de 6.4 §8). Mutuamente excluyente con `ANAMNESIS` en la
    #: misma sesión — ver `applies_to()` de ambos steps.
    SESSION_NOTES = "session_notes"


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
#: enriquecimiento opcional — ver `PatientSummaryStep`. `SESSION_NOTES`
#: (Fase 6.4.3) se inserta justo después de `ANAMNESIS`: ambos son
#: mutuamente excluyentes vía `applies_to()` y ninguno depende del otro
#: formalmente — la posición solo refleja que son "la alternativa" uno
#: del otro, no un requisito de `depends_on()`.
PIPELINE_STEP_ORDER: tuple[AIArtifactType, ...] = (
    AIArtifactType.TRANSCRIPT,
    AIArtifactType.SUMMARY,
    AIArtifactType.PATIENT_SUMMARY,
    AIArtifactType.CLINICAL_FLAGS,
    AIArtifactType.MISSING_INFORMATION,
    AIArtifactType.ANAMNESIS,
    AIArtifactType.SESSION_NOTES,
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
    #: Identidad del baseline exacto (Hito 6.5.3, RFC técnico de 6.5 §11)
    #: sobre el que se generó este artefacto, SOLO cuando es una propuesta
    #: de `AnamnesisUpdateStep` — `None` para cualquier otro artefacto
    #: (anamnesis inicial incluida) y para el resto de `artifact_type`.
    #: Nunca cambian tras la creación: ni `edit_content`, ni una nueva
    #: versión generada, ni `approve`/`reject` los tocan — son la
    #: identidad del baseline ORIGINAL de la propuesta, usada para
    #: optimistic concurrency al aprobar (ver `AIPipelineService._set_disposition`).
    baseline_artifact_id: uuid.UUID | None = None
    baseline_version_id: uuid.UUID | None = None


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
