"""Entidad de dominio Consent y su enum. Sin dependencias de SQLAlchemy.

Ver docs/data-model.md §2 (`consents`) y docs/fase-6-rfc.md §9.1
(prerrequisito 5, hito 6.0). Módulo propio, sin servicio ni endpoint
todavía — solo la infraestructura que `AIPipelineService` necesita para
comprobar el consentimiento de `procesamiento_ia`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ConsentType(StrEnum):
    GRABACION_AUDIO = "grabacion_audio"
    PROCESAMIENTO_IA = "procesamiento_ia"
    ALMACENAMIENTO = "almacenamiento"


@dataclass(slots=True)
class Consent:
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    clinical_session_id: uuid.UUID | None
    consent_type: ConsentType
    granted: bool
    consent_version: str | None
    granted_by: uuid.UUID
    recorded_at: datetime | None
    notes: str | None
