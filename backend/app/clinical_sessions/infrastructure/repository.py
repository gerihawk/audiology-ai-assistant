"""Implementación SQLAlchemy del repositorio de sesiones clínicas."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinical_sessions.domain.entities import (
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)
from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM


def _to_domain(row: ClinicalSessionORM) -> ClinicalSession:
    return ClinicalSession(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        professional_id=row.professional_id,
        session_type=SessionType(row.session_type),
        status=ClinicalSessionStatus(row.status),
        scheduled_at=row.scheduled_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        title=row.title,
        administrative_notes=row.administrative_notes,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        schema_version=row.schema_version,
        is_archived=row.is_archived,
        archived_at=row.archived_at,
    )


def _day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = datetime.combine(day, time.max, tzinfo=UTC)
    return start, end


class SqlAlchemyClinicalSessionRepository:
    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, session_id: uuid.UUID
    ) -> ClinicalSession | None:
        result = await session.execute(
            select(ClinicalSessionORM).where(
                ClinicalSessionORM.id == session_id, ClinicalSessionORM.clinic_id == clinic_id
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

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
    ) -> tuple[list[ClinicalSession], int]:
        filters = [ClinicalSessionORM.clinic_id == clinic_id]
        if not include_archived:
            filters.append(ClinicalSessionORM.is_archived.is_(False))
        if patient_id is not None:
            filters.append(ClinicalSessionORM.patient_id == patient_id)
        if professional_id is not None:
            filters.append(ClinicalSessionORM.professional_id == professional_id)
        if status is not None:
            filters.append(ClinicalSessionORM.status == status.value)
        if session_type is not None:
            filters.append(ClinicalSessionORM.session_type == session_type.value)
        if scheduled_from is not None:
            filters.append(ClinicalSessionORM.scheduled_at >= _day_bounds_utc(scheduled_from)[0])
        if scheduled_to is not None:
            filters.append(ClinicalSessionORM.scheduled_at <= _day_bounds_utc(scheduled_to)[1])
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    ClinicalSessionORM.title.ilike(pattern),
                    ClinicalSessionORM.administrative_notes.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(ClinicalSessionORM).where(*filters)
        total = (await session.execute(count_stmt)).scalar_one()

        list_stmt = (
            select(ClinicalSessionORM)
            .where(*filters)
            .order_by(ClinicalSessionORM.created_at.asc(), ClinicalSessionORM.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await session.execute(list_stmt)).scalars().all()
        return [_to_domain(row) for row in rows], total

    async def add(
        self, session: AsyncSession, clinical_session: ClinicalSession
    ) -> ClinicalSession:
        row = ClinicalSessionORM(
            id=clinical_session.id,
            clinic_id=clinical_session.clinic_id,
            patient_id=clinical_session.patient_id,
            professional_id=clinical_session.professional_id,
            session_type=clinical_session.session_type.value,
            status=clinical_session.status.value,
            scheduled_at=clinical_session.scheduled_at,
            started_at=clinical_session.started_at,
            ended_at=clinical_session.ended_at,
            title=clinical_session.title,
            administrative_notes=clinical_session.administrative_notes,
            reviewed_by=clinical_session.reviewed_by,
            reviewed_at=clinical_session.reviewed_at,
            created_by=clinical_session.created_by,
            updated_by=clinical_session.updated_by,
            schema_version=clinical_session.schema_version,
            is_archived=clinical_session.is_archived,
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
        session_id: uuid.UUID,
        values: dict[str, Any],
    ) -> ClinicalSession | None:
        result = await session.execute(
            select(ClinicalSessionORM).where(
                ClinicalSessionORM.id == session_id, ClinicalSessionORM.clinic_id == clinic_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if isinstance(value, (SessionType, ClinicalSessionStatus)):
                value = value.value
            setattr(row, key, value)
        await session.flush()
        return _to_domain(row)
