"""Contexto longitudinal ya resuelto por `AIPipelineService` antes de
invocar al orquestador — ver docs/fase-6-rfc.md §3.1/§3.4 y el RFC técnico
de la Fase 6.4, hito 6.4.1.

Ningún tipo de este módulo transporta un `AsyncSession` ni un
repositorio: `LoadedPatientContext` es siempre un snapshot en memoria, ya
cargado, nunca una vía de acceso diferida a base de datos — el mismo
principio que ya aplican `cost_budget`/`retry_config` en
`PipelineExecutionContext` desde la Fase 6.1. `PipelineStep.applies_to()`
solo puede leer estos valores, nunca ampliarlos con una consulta propia.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.integrations.domain.missing_information_generator import MissingInformationTarget


class PatientContextRequirement(StrEnum):
    """Requisitos declarativos de contexto longitudinal que un
    `PipelineStep` puede exigir vía `patient_context_requirements()`. Sin
    framework genérico de consultas: cada miembro es una necesidad de
    dominio concreta, añadida solo cuando un step real la necesita — ver
    RFC técnico de 6.4 §6 (no strings mágicos, no requisitos futuros
    inventados)."""

    PREVIOUS_APPROVED_ANAMNESIS = "previous_approved_anamnesis"


@dataclass(slots=True, frozen=True)
class PreviousAnamnesisRef:
    """Referencia mínima a la última `ANAMNESIS` aprobada de OTRA sesión
    clínica del mismo paciente — nunca la sesión actual (ver Decisión
    final 1 del RFC técnico de 6.4.1). `content` es el mismo `dict`
    persistido en `AIArtifactVersion.content` (sin retipar aquí): una
    representación más estricta solo tiene sentido cuando algo la
    consuma de verdad (hito 6.4.2+), no antes."""

    clinical_session_id: uuid.UUID
    approved_at: datetime
    content: dict[str, Any]


@dataclass(slots=True, frozen=True)
class LoadedPatientContext:
    """Contexto longitudinal completo de un *run* del pipeline — resuelto
    una única vez por `AIPipelineService`, nunca por step individual.

    `session_type` es el `.value` de `SessionType` (`clinical_sessions`),
    nunca el propio enum: `ai_pipeline`/`integrations` no importan
    vocabulario de otro módulo de dominio (mismo principio que separa
    `ClinicalSessionStatus` de `ProcessingStatus`, ver
    docs/architecture.md). `None` es válido — sesión legacy sin tipo
    determinado, ver docs/fase-6-rfc.md §3.3."""

    session_type: str | None
    previous_approved_anamnesis: PreviousAnamnesisRef | None


def resolve_missing_information_target(
    patient_context: LoadedPatientContext | None,
) -> MissingInformationTarget | None:
    """Única fuente de verdad de la decisión binaria "anamnesis previa
    aprobada, sí o no" — Fase 6.4.4, RFC técnico de 6.4 §3/§10. Pura, sin
    I/O: reutilizada por `AnamnesisStep.applies_to()`,
    `SessionNotesStep.applies_to()` y `MissingInformationStep`, para que
    los tres deriven siempre del mismo `LoadedPatientContext` sin
    reglas duplicadas que puedan divergir.

    `None` únicamente cuando `patient_context` nunca se cargó — caso
    defensivo, hoy inalcanzable en producción una vez que los tres steps
    declaran `PREVIOUS_APPROVED_ANAMNESIS` en
    `patient_context_requirements()`. Nunca se inventa un target por
    defecto: cada llamador decide qué hacer con `None` (ver
    `MissingInformationStep.applies_to()`)."""
    if patient_context is None:
        return None
    if patient_context.previous_approved_anamnesis is None:
        return MissingInformationTarget.ANAMNESIS_FIELDS
    return MissingInformationTarget.SESSION_NOTES_BLOCKS
