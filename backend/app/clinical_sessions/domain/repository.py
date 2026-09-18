"""Puerto del repositorio de sesiones clínicas.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinical_sessions.domain.entities import (
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)


class ClinicalSessionRepository(Protocol):
    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, session_id: uuid.UUID
    ) -> ClinicalSession | None: ...

    async def list(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        patient_id: uuid.UUID | None,
        professional_id: uuid.UUID | None,
        status: ClinicalSessionStatus | None,
        session_type: SessionType | None,
        scheduled_from: date | None,
        scheduled_to: date | None,
        search: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[ClinicalSession], int]: ...

    async def add(
        self, session: AsyncSession, clinical_session: ClinicalSession
    ) -> ClinicalSession: ...

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        session_id: uuid.UUID,
        values: dict[str, Any],
    ) -> ClinicalSession | None: ...

    async def list_all_by_patient(
        self, session: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> list[ClinicalSession]:
        """TODAS las sesiones clínicas del paciente (incluidas
        archivadas), sin paginar — a diferencia de `list()`. Usado
        exclusivamente por `RetentionCleanupService.
        purge_patient_clinical_data()`, que necesita el conjunto completo
        para la purga, nunca una página."""
        ...

    async def delete_all(
        self, session: AsyncSession, clinic_id: uuid.UUID, session_ids: list[uuid.UUID]
    ) -> int:
        """Borrado físico definitivo de `clinical_sessions` — usado
        exclusivamente por `RetentionCleanupService.
        purge_patient_clinical_data()`, como último paso de la purga
        (una vez borrados ya `audio_recordings`/`ai_pipeline_runs`/
        `ai_generation_runs`/`ai_artifacts` de estas sesiones, que de lo
        contrario bloquearían el borrado por FK). Devuelve el nº de filas
        eliminadas."""
        ...
