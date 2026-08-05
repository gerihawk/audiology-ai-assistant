"""Repositorio mínimo de Clinic: sin API propia en la Fase 2, usado por el seed."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.orm import ClinicORM


def _to_domain(row: ClinicORM) -> Clinic:
    return Clinic(
        id=row.id,
        name=row.name,
        code=row.code,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyClinicRepository:
    async def get_by_code(self, session: AsyncSession, code: str) -> Clinic | None:
        result = await session.execute(select(ClinicORM).where(ClinicORM.code == code))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, session: AsyncSession, clinic_id: uuid.UUID) -> Clinic | None:
        result = await session.execute(select(ClinicORM).where(ClinicORM.id == clinic_id))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def add(self, session: AsyncSession, clinic: Clinic) -> None:
        session.add(
            ClinicORM(
                id=clinic.id,
                name=clinic.name,
                code=clinic.code,
                is_active=clinic.is_active,
            )
        )
