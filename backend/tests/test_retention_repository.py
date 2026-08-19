"""Repositorio de retención (`AudioRecordingRepository.list_expired`) —
Fase 7.2 (docs/development-plan.md)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.clinical_sessions.domain.entities import ClinicalSession
from app.core.processing_status import ProcessingStatus
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, create_audio_recording, create_clinical_session

_CUTOFF = datetime.now(UTC) - timedelta(days=30)
_OLD = _CUTOFF - timedelta(days=1)
_RECENT = _CUTOFF + timedelta(days=1)


@pytest_asyncio.fixture
async def clinical_session(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
) -> ClinicalSession:
    return await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )


async def test_list_expired_excludes_recordings_uploaded_after_cutoff(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_RECENT
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, clinic_with_users.clinic.id, _CUTOFF
    )

    assert result == []


async def test_list_expired_includes_recordings_uploaded_before_cutoff(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    old = await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, clinic_with_users.clinic.id, _CUTOFF
    )

    assert [item.id for item in result] == [old.id]


async def test_list_expired_excludes_already_deleted_recordings(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        status=ProcessingStatus.DELETED,
        uploaded_at=_OLD,
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, clinic_with_users.clinic.id, _CUTOFF
    )

    assert result == []


async def test_list_expired_includes_stuck_failed_and_uploaded_recordings(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    failed = await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        status=ProcessingStatus.FAILED,
        uploaded_at=_OLD,
    )
    validating = await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        status=ProcessingStatus.VALIDATING,
        uploaded_at=_OLD,
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, clinic_with_users.clinic.id, _CUTOFF
    )

    assert {item.id for item in result} == {failed.id, validating.id}


async def test_list_expired_orders_oldest_first(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    newer = await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        uploaded_at=_CUTOFF - timedelta(days=1),
    )
    older = await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        uploaded_at=_CUTOFF - timedelta(days=10),
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, clinic_with_users.clinic.id, _CUTOFF
    )

    assert [item.id for item in result] == [older.id, newer.id]


async def test_list_expired_is_isolated_by_clinic(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )

    result = await SqlAlchemyAudioRecordingRepository().list_expired(
        db_session, uuid.uuid4(), _CUTOFF
    )

    assert result == []
