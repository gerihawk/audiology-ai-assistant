"""Repositorio de consentimientos — infraestructura preparada en el hito
6.0 de la Fase 6 (docs/fase-6-rfc.md §9.1) para el bloqueo de
`AIPipelineService.run_pipeline`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.consents.domain.entities import Consent, ConsentType
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers


def _consent(
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    granted_by: uuid.UUID,
    granted: bool,
    version: str,
) -> Consent:
    return Consent(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        clinical_session_id=None,
        consent_type=ConsentType.PROCESAMIENTO_IA,
        granted=granted,
        consent_version=version,
        granted_by=granted_by,
        recorded_at=None,
        notes=None,
    )


async def test_get_latest_returns_none_when_no_consent_recorded(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    repo = SqlAlchemyConsentRepository()

    result = await repo.get_latest(
        db_session, clinic_with_users.clinic.id, patient.id, ConsentType.PROCESAMIENTO_IA
    )

    assert result is None


async def test_get_latest_returns_the_most_recently_recorded_consent(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    repo = SqlAlchemyConsentRepository()

    await repo.add(
        db_session,
        _consent(
            clinic_id=clinic_with_users.clinic.id,
            patient_id=patient.id,
            granted_by=clinic_with_users.admin.id,
            granted=True,
            version="1.0",
        ),
    )
    await db_session.commit()  # transacciones separadas -> recorded_at distinto y determinista

    await repo.add(
        db_session,
        _consent(
            clinic_id=clinic_with_users.clinic.id,
            patient_id=patient.id,
            granted_by=clinic_with_users.admin.id,
            granted=False,
            version="1.0",
        ),
    )
    await db_session.commit()

    result = await repo.get_latest(
        db_session, clinic_with_users.clinic.id, patient.id, ConsentType.PROCESAMIENTO_IA
    )

    assert result is not None
    assert result.granted is False  # la revocación posterior es la vigente


async def test_get_latest_is_isolated_by_clinic(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    repo = SqlAlchemyConsentRepository()
    await repo.add(
        db_session,
        _consent(
            clinic_id=clinic_with_users.clinic.id,
            patient_id=patient.id,
            granted_by=clinic_with_users.admin.id,
            granted=True,
            version="1.0",
        ),
    )
    await db_session.commit()

    result = await repo.get_latest(
        db_session, uuid.uuid4(), patient.id, ConsentType.PROCESAMIENTO_IA
    )

    assert result is None
