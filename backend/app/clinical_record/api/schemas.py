"""Esquemas Pydantic de la vista longitudinal de historia clínica — Hito
6.7.4 (docs/fase-6-rfc.md §7.2/§7.5, scope=patient).

Deliberadamente separados de los DTOs de dominio (`ClinicalRecordPage`/
`ClinicalRecordSessionEntry`/`ClinicalRecordDocument`, hito 6.7.1): la API
nunca serializa dataclasses de dominio directamente, mismo criterio que
`patients/api/schemas.py`. El contenido ya llega saneado (sin
`source_excerpt`) desde el dominio — este módulo no vuelve a sanear nada,
solo mapea campo a campo.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai_pipeline.domain.entities import AIArtifactType, ruleset_disclaimer_for
from app.clinical_record.domain.entities import (
    ClinicalRecordDocument,
    ClinicalRecordPage,
    ClinicalRecordSessionEntry,
)
from app.core.messages.es import AI_DISCLAIMER

__all__ = [
    "ClinicalRecordDocumentResponse",
    "ClinicalRecordSessionEntryResponse",
    "ClinicalRecordPageResponse",
]


class ClinicalRecordDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_artifact_id: uuid.UUID
    artifact_type: AIArtifactType
    version_number: int
    approved_by: uuid.UUID
    approved_at: datetime
    content: dict[str, Any]
    is_current_baseline: bool
    #: docs/clinical-safety.md §7 — obligatorio junto a `CLINICAL_FLAGS`,
    #: `None` para el resto de `artifact_type` (mismo criterio que los
    #: exportadores PDF/texto, que solo lo imprimen en ese bloque).
    ruleset_disclaimer: str | None = None

    @classmethod
    def from_domain(cls, document: ClinicalRecordDocument) -> ClinicalRecordDocumentResponse:
        return cls(
            ai_artifact_id=document.ai_artifact_id,
            artifact_type=document.artifact_type,
            version_number=document.version_number,
            approved_by=document.approved_by,
            approved_at=document.approved_at,
            content=document.content,
            is_current_baseline=document.is_current_baseline,
            ruleset_disclaimer=ruleset_disclaimer_for(document.artifact_type),
        )


class ClinicalRecordSessionEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinical_session_id: uuid.UUID
    session_type: str | None
    created_at: datetime
    documents: list[ClinicalRecordDocumentResponse]

    @classmethod
    def from_domain(cls, entry: ClinicalRecordSessionEntry) -> ClinicalRecordSessionEntryResponse:
        return cls(
            clinical_session_id=entry.clinical_session_id,
            session_type=entry.session_type,
            created_at=entry.created_at,
            documents=[
                ClinicalRecordDocumentResponse.from_domain(document) for document in entry.documents
            ],
        )


class ClinicalRecordPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: uuid.UUID
    patient_internal_code: str
    patient_display_name: str | None
    sessions: list[ClinicalRecordSessionEntryResponse]
    total: int
    limit: int
    offset: int
    ai_disclaimer: str = AI_DISCLAIMER

    @classmethod
    def from_page(cls, page: ClinicalRecordPage) -> ClinicalRecordPageResponse:
        return cls(
            patient_id=page.patient.patient_id,
            patient_internal_code=page.patient.internal_code,
            patient_display_name=page.patient.display_name,
            sessions=[
                ClinicalRecordSessionEntryResponse.from_domain(entry) for entry in page.sessions
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )
