"""Tests de integración de /api/v1/retention/expired-audio — Fase 7.2
(docs/development-plan.md). Permisos (solo admin), idempotencia de la
purga y auditoría (`audio_recording.deleted` por registro +
`retention.purge_executed` como resumen)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.clinical_sessions.domain.entities import ClinicalSession
from app.core.config import get_settings
from app.core.processing_status import ProcessingStatus
from app.patients.domain.entities import Patient
from tests.factories import (
    ClinicWithUsers,
    create_audio_recording,
    create_clinical_session,
    dev_headers,
)

_OLD = datetime.now(UTC) - timedelta(days=get_settings().retention_days_default + 1)
_RECENT = datetime.now(UTC) - timedelta(days=1)


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


# --- Permisos: solo admin, ni siquiera audiologist -----------------------


async def test_admin_can_list_expired_audio(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: ClinicalSession
):
    response = await api_client.get(
        "/api/v1/retention/expired-audio", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_list_expired_audio_forbidden_for_non_admin(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, role_attr: str
):
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.get("/api/v1/retention/expired-audio", headers=dev_headers(user))
    assert response.status_code == 403


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_purge_expired_audio_forbidden_for_non_admin(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, role_attr: str
):
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.post(
        "/api/v1/retention/expired-audio/purge", headers=dev_headers(user)
    )
    assert response.status_code == 403


# --- Listado: respeta el corte, incluye estados atascados ----------------


async def test_list_expired_audio_includes_stuck_and_excludes_recent(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    clinical_session: ClinicalSession,
):
    expired = await create_audio_recording(
        db_session,
        clinical_session.id,
        clinic_with_users.admin.id,
        status=ProcessingStatus.FAILED,
        uploaded_at=_OLD,
    )
    await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_RECENT
    )

    response = await api_client.get(
        "/api/v1/retention/expired-audio", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(expired.id)]


# --- Purga: idempotente, borrado físico, auditoría ------------------------


async def test_purge_deletes_expired_audio_and_is_idempotent(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    clinical_session: ClinicalSession,
):
    expired = await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )

    first_purge = await api_client.post(
        "/api/v1/retention/expired-audio/purge", headers=dev_headers(clinic_with_users.admin)
    )
    assert first_purge.status_code == 200, first_purge.text
    assert [item["id"] for item in first_purge.json()["items"]] == [str(expired.id)]
    assert first_purge.json()["items"][0]["status"] == "deleted"

    listing = await api_client.get(
        "/api/v1/retention/expired-audio", headers=dev_headers(clinic_with_users.admin)
    )
    assert listing.json()["items"] == []

    second_purge = await api_client.post(
        "/api/v1/retention/expired-audio/purge", headers=dev_headers(clinic_with_users.admin)
    )
    assert second_purge.status_code == 200
    assert second_purge.json()["items"] == []


async def test_purge_with_nothing_expired_does_not_fail_or_audit(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    clinical_session: ClinicalSession,
):
    await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_RECENT
    )

    response = await api_client.post(
        "/api/v1/retention/expired-audio/purge", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

    result = await db_session.execute(
        select(AuditLogORM).where(AuditLogORM.action == "retention.purge_executed")
    )
    assert result.scalars().all() == []


async def test_purge_writes_per_record_and_summary_audit_entries(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    clinical_session: ClinicalSession,
):
    first = await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )
    second = await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )

    response = await api_client.post(
        "/api/v1/retention/expired-audio/purge", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {str(first.id), str(second.id)}

    deleted_entries = (
        (
            await db_session.execute(
                select(AuditLogORM).where(AuditLogORM.action == "audio_recording.deleted")
            )
        )
        .scalars()
        .all()
    )
    assert {entry.entity_id for entry in deleted_entries} == {first.id, second.id}

    summary_entries = (
        (
            await db_session.execute(
                select(AuditLogORM).where(AuditLogORM.action == "retention.purge_executed")
            )
        )
        .scalars()
        .all()
    )
    assert len(summary_entries) == 1
    summary = summary_entries[0]
    assert summary.audit_metadata["purged_count"] == 2
    assert set(summary.audit_metadata["audio_recording_ids"]) == {str(first.id), str(second.id)}
