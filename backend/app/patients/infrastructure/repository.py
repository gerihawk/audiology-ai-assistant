"""Implementación SQLAlchemy del repositorio de pacientes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.patients.domain.entities import Patient, Sex
from app.patients.infrastructure.orm import PatientORM


def _to_domain(row: PatientORM) -> Patient:
    return Patient(
        id=row.id,
        clinic_id=row.clinic_id,
        internal_code=row.internal_code,
        display_name=row.display_name,
        birth_year=row.birth_year,
        sex=Sex(row.sex) if row.sex else None,
        preferred_language=row.preferred_language,
        notes=row.notes,
        is_archived=row.is_archived,
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
        schema_version=row.schema_version,
    )


class SqlAlchemyPatientRepository:
    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Patient | None:
        result = await session.execute(
            select(PatientORM).where(PatientORM.id == patient_id, PatientORM.clinic_id == clinic_id)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_internal_code(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        internal_code: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> Patient | None:
        stmt = select(PatientORM).where(
            PatientORM.clinic_id == clinic_id, PatientORM.internal_code == internal_code
        )
        if exclude_id is not None:
            stmt = stmt.where(PatientORM.id != exclude_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        search: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Patient], int]:
        filters = [PatientORM.clinic_id == clinic_id]
        if not include_archived:
            filters.append(PatientORM.is_archived.is_(False))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    PatientORM.internal_code.ilike(pattern),
                    PatientORM.display_name.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(PatientORM).where(*filters)
        total = (await session.execute(count_stmt)).scalar_one()

        list_stmt = (
            select(PatientORM)
            .where(*filters)
            .order_by(PatientORM.created_at.asc(), PatientORM.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await session.execute(list_stmt)).scalars().all()
        return [_to_domain(row) for row in rows], total

    async def add(self, session: AsyncSession, patient: Patient) -> Patient:
        row = PatientORM(
            id=patient.id,
            clinic_id=patient.clinic_id,
            internal_code=patient.internal_code,
            display_name=patient.display_name,
            birth_year=patient.birth_year,
            sex=patient.sex.value if patient.sex else None,
            preferred_language=patient.preferred_language,
            notes=patient.notes,
            is_archived=patient.is_archived,
            created_by=patient.created_by,
            updated_by=patient.updated_by,
            schema_version=patient.schema_version,
        )
        session.add(row)
        await session.flush()
        # created_at/updated_at los fija PostgreSQL (server_default); se
        # leen de vuelta para que la entidad devuelta refleje el valor real.
        return _to_domain(row)

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        patient_id: uuid.UUID,
        values: dict[str, Any],
    ) -> Patient | None:
        result = await session.execute(
            select(PatientORM).where(PatientORM.id == patient_id, PatientORM.clinic_id == clinic_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if key == "sex" and isinstance(value, Sex):
                value = value.value
            setattr(row, key, value)
        await session.flush()
        return _to_domain(row)
