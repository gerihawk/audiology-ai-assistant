"""Puerto del repositorio de sesiones clínicas.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
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

    async def count_by_status_for_clinic(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        created_since: datetime,
        professional_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """Fase 15 (analítica/reporting) — agregación por
        `ClinicalSessionStatus.value`, filtrada por `created_at >=
        created_since` (no `scheduled_at`, a diferencia de `list()`: aquí
        interesa cuándo se dio de alta la sesión en el sistema, no cuándo
        está programada). Excluye siempre archivadas. `professional_id`
        acota a un único profesional (vista "own" de un `audiologist`,
        ver `AnalyticsService`) — `None` agrega toda la clínica (vista de
        `admin`). Solo incluye los estados con al menos una fila; el
        llamador rellena a 0 los que falten."""
        ...

    async def count_per_day_for_clinic(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        created_since: datetime,
        professional_id: uuid.UUID | None = None,
    ) -> list[tuple[date, int]]:
        """Fase 15 — serie temporal de sesiones creadas por día (UTC),
        para el gráfico de tendencia del panel de analítica. Mismos
        filtros que `count_by_status_for_clinic`. Ordenada
        cronológicamente; solo incluye días con al menos una sesión (el
        llamador rellena los huecos si el frontend lo necesita)."""
        ...

    async def count_by_professional_for_clinic(
        self, session: AsyncSession, clinic_id: uuid.UUID, *, created_since: datetime
    ) -> list[tuple[uuid.UUID, int]]:
        """Fase 15 — actividad por profesional (sesiones creadas en el
        periodo), ordenada de mayor a menor. Solo para la vista `admin`
        del panel de analítica (`AnalyticsService`) — nunca se expone a
        `audiologist`, que solo ve su propio recuento."""
        ...
