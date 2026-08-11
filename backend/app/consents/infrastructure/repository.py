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
