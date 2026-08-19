"""Tests de `_resolve_admin_per_clinic` (backend/app/retention/cli.py):
lógica pura de agrupación de usuarios por clínica, sin base de datos. Más
abajo, test de integración end-to-end del comando completo (Fase 8.2),
mismo patrón de aserciones que test_retention_api.py (Fase 7.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.audio.infrastructure.orm import AudioRecordingORM
from app.audit_log.infrastructure.orm import AuditLogORM
from app.clinical_sessions.domain.entities import ClinicalSession
from app.core.config import get_settings
from app.patients.domain.entities import Patient
from app.retention.cli import _resolve_admin_per_clinic, main
from app.users.domain.entities import Role, User
from tests.factories import (
    ClinicWithUsers,
    create_audio_recording,
    create_clinical_session,
)

_NOW = datetime.now(UTC)
_OLD = datetime.now(UTC) - timedelta(days=get_settings().retention_days_default + 1)


def _user(clinic_id: uuid.UUID, role: Role, is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        email=f"{uuid.uuid4()}@dev.local",
        display_name="Usuario ficticio",
        role=role,
        is_active=is_active,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_first_active_admin_per_clinic_wins() -> None:
    clinic_a, clinic_b = uuid.uuid4(), uuid.uuid4()
    first_admin_a = _user(clinic_a, Role.ADMIN)
    second_admin_a = _user(clinic_a, Role.ADMIN)
    admin_b = _user(clinic_b, Role.ADMIN)
    users = [first_admin_a, second_admin_a, admin_b]

    result = _resolve_admin_per_clinic(users)

    assert result == {clinic_a: first_admin_a, clinic_b: admin_b}


def test_clinic_without_active_admin_is_omitted() -> None:
    clinic_no_admin = uuid.uuid4()
    users = [
        _user(clinic_no_admin, Role.AUDIOLOGIST),
        _user(clinic_no_admin, Role.ADMIN, is_active=False),
    ]

    assert _resolve_admin_per_clinic(users) == {}


# --- Integración end-to-end: main() purga de verdad, vía la BD de test ---


async def test_main_purges_expired_audio_and_writes_summary_audit_entry(
    test_engine: AsyncEngine,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
) -> None:
    clinical_session: ClinicalSession = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    expired = await create_audio_recording(
        db_session, clinical_session.id, clinic_with_users.admin.id, uploaded_at=_OLD
    )

    # `main()` recibe el session_factory de la BD de test aislada (no el
    # global de `app.core.db`, que apuntaría a la BD de desarrollo real).
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    await main(test_session_factory)

    audio_row = (
        await db_session.execute(
            select(AudioRecordingORM).where(AudioRecordingORM.id == expired.id)
        )
    ).scalar_one()
    assert audio_row.status == "deleted"

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
    assert summary.clinic_id == clinic_with_users.clinic.id
    assert summary.audit_metadata["purged_count"] == 1
    assert summary.audit_metadata["audio_recording_ids"] == [str(expired.id)]


if __name__ == "__main__":
    test_first_active_admin_per_clinic_wins()
    test_clinic_without_active_admin_is_omitted()
    print("ok")
