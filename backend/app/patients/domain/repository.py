"""Puerto del repositorio de pacientes.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
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

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        patient_id: uuid.UUID,
        values: dict[str, Any],
    ) -> Patient | None: ...
