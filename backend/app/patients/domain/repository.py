"""Puerto del repositorio de pacientes.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.patients.domain.entities import Patient


class PatientRepository(Protocol):
    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Patient | None: ...

    async def get_by_internal_code(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        internal_code: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> Patient | None: ...

    async def list(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        search: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Patient], int]: ...

    async def add(self, session: AsyncSession, patient: Patient) -> Patient: ...

    async def count_for_clinic(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        created_since: datetime | None = None,
        include_archived: bool = False,
    ) -> int:
        """Fase 15 (analítica/reporting) — conteo agregado, sin traer
        filas: `created_since=None` da el total; con fecha, los pacientes
        nuevos desde esa fecha. `include_archived=False` por defecto,
        mismo criterio por defecto que `list()`."""
        ...

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        patient_id: uuid.UUID,
        values: dict[str, Any],
    ) -> Patient | None: ...
