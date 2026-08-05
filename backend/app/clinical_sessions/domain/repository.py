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
