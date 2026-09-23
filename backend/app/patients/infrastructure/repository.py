"""Implementación SQLAlchemy del repositorio de pacientes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
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
        identity_purged_at=row.identity_purged_at,
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

        if not search:
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

        # `display_name` está cifrado a nivel de aplicación desde
        # 2026-09-18 (ver app/core/field_encryption.py) con un nonce
        # aleatorio por valor: el ciphertext nunca es igual para el mismo
        # texto en claro, así que un `ilike` de SQL sobre esa columna ya
        # no puede funcionar (dejó de poder desde que se cifró, no es una
        # regresión de esta función). `internal_code` sigue en claro y sí
        # sería filtrable en SQL, pero como el término de búsqueda puede
        # coincidir con cualquiera de los dos campos (mismo comportamiento
        # que antes de cifrar nada — ver
        # tests/test_patients_api.py::test_search_by_internal_code_and_display_name),
        # el filtro combinado se resuelve en Python: se trae el conjunto
        # ya acotado por clinic_id/is_archived (sigue siendo SQL, nunca
        # toda la tabla) y se descifra/filtra en memoria, replicando el
        # mismo criterio de "subcadena, insensible a mayúsculas, no a
        # acentos" que ya tenía `ilike`. Coste proporcional al tamaño de
        # una clínica, no de toda la base de datos — aceptable a la escala
        # actual del producto; documentado como límite conocido en
        # docs/privacy-and-security.md §4 si algún día una clínica crece
        # lo bastante como para que esto deje de ser trivial.
        pattern = search.lower()
        all_stmt = (
            select(PatientORM)
            .where(*filters)
            .order_by(PatientORM.created_at.asc(), PatientORM.id.asc())
        )
        all_rows = (await session.execute(all_stmt)).scalars().all()
        matches = [
            row
            for row in all_rows
            if pattern in row.internal_code.lower()
            or (row.display_name is not None and pattern in row.display_name.lower())
        ]
        total = len(matches)
        page = matches[offset : offset + limit]
        return [_to_domain(row) for row in page], total

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

    async def count_for_clinic(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        created_since: datetime | None = None,
        include_archived: bool = False,
    ) -> int:
        filters = [PatientORM.clinic_id == clinic_id]
        if not include_archived:
            filters.append(PatientORM.is_archived.is_(False))
        if created_since is not None:
            filters.append(PatientORM.created_at >= created_since)
        stmt = select(func.count()).select_from(PatientORM).where(*filters)
        return (await session.execute(stmt)).scalar_one()

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
