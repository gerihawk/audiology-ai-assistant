"""Implementación SQLAlchemy del repositorio de consentimientos."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents.domain.entities import Consent, ConsentType
from app.consents.infrastructure.orm import ConsentORM


def _to_domain(row: ConsentORM) -> Consent:
    return Consent(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        clinical_session_id=row.clinical_session_id,
        consent_type=ConsentType(row.consent_type),
        granted=row.granted,
        consent_version=row.consent_version,
        granted_by=row.granted_by,
        recorded_at=row.recorded_at,
        notes=row.notes,
    )


class SqlAlchemyConsentRepository:
    async def add(self, session: AsyncSession, consent: Consent) -> Consent:
        row = ConsentORM(
            id=consent.id,
            clinic_id=consent.clinic_id,
            patient_id=consent.patient_id,
            clinical_session_id=consent.clinical_session_id,
            consent_type=consent.consent_type.value,
            granted=consent.granted,
            consent_version=consent.consent_version,
            granted_by=consent.granted_by,
            notes=consent.notes,
        )
        session.add(row)
        await session.flush()
        return _to_domain(row)

    async def get_latest(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        patient_id: uuid.UUID,
        consent_type: ConsentType,
    ) -> Consent | None:
        result = await session.execute(
            select(ConsentORM)
            .where(
                ConsentORM.clinic_id == clinic_id,
                ConsentORM.patient_id == patient_id,
                ConsentORM.consent_type == consent_type.value,
            )
            .order_by(ConsentORM.recorded_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_by_patient(
        self, session: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> list[Consent]:
        # `ix_consents_patient_type` (patient_id, consent_type) ya cubre el
        # filtro por `patient_id` como prefijo izquierdo — suficiente aquí:
        # no se añade un índice nuevo por `recorded_at`. El volumen por
        # paciente es del orden de unidades/decenas de registros (un
        # consentimiento se registra por evento, no por sesión ni de forma
        # masiva), así que el `ORDER BY` sin índice dedicado ordena en
        # memoria un conjunto trivial — el coste de mantenimiento de un
        # índice adicional no se justifica con este volumen.
        result = await session.execute(
            select(ConsentORM)
            .where(ConsentORM.clinic_id == clinic_id, ConsentORM.patient_id == patient_id)
            .order_by(ConsentORM.recorded_at.desc())
        )
        return [_to_domain(row) for row in result.scalars()]
