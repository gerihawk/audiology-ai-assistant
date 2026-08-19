"""Helpers para crear clínicas/usuarios ficticios directamente vía repositorio en los tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.domain.entities import AudioRecording
from app.audio.infrastructure.orm import AudioRecordingORM
from app.clinical_sessions.domain.entities import (
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.current_user import CurrentUser
from app.core.processing_status import ProcessingStatus
from app.integrations.domain.integration_config import IntegrationConfig, IntegrationName
from app.integrations.infrastructure.orm import IntegrationConfigORM
from app.patients.domain.entities import Patient
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository


def _now() -> datetime:
    return datetime.now(UTC)


async def create_clinic(
    session: AsyncSession, *, code: str | None = None, name: str = "Clínica de test"
) -> Clinic:
    clinic = Clinic(
        id=uuid.uuid4(),
        name=name,
        code=code or f"TEST-{uuid.uuid4().hex[:8]}",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    await SqlAlchemyClinicRepository().add(session, clinic)
    await session.commit()
    return clinic


async def create_user(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    *,
    role: Role,
    email: str | None = None,
    display_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.local",
        display_name=display_name or f"Usuario {role.value} de test",
        role=role,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )
    await SqlAlchemyUserRepository().add(session, user)
    await session.commit()
    return user


@dataclass(slots=True)
class ClinicWithUsers:
    clinic: Clinic
    admin: User
    audiologist: User
    viewer: User


async def create_clinic_with_users(session: AsyncSession) -> ClinicWithUsers:
    clinic = await create_clinic(session)
    admin = await create_user(session, clinic.id, role=Role.ADMIN)
    audiologist = await create_user(session, clinic.id, role=Role.AUDIOLOGIST)
    viewer = await create_user(session, clinic.id, role=Role.VIEWER)
    return ClinicWithUsers(clinic=clinic, admin=admin, audiologist=audiologist, viewer=viewer)


async def create_patient(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    internal_code: str | None = None,
    is_archived: bool = False,
) -> Patient:
    patient = Patient(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        internal_code=internal_code or f"PAT-{uuid.uuid4().hex[:8].upper()}",
        display_name="Paciente de test",
        birth_year=1980,
        sex=None,
        preferred_language="es",
        notes=None,
        is_archived=is_archived,
        created_by=created_by,
        updated_by=created_by,
        created_at=_now(),
        updated_at=_now(),
        archived_at=_now() if is_archived else None,
        schema_version=1,
    )
    await SqlAlchemyPatientRepository().add(session, patient)
    await session.commit()
    return patient


async def create_clinical_session(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    professional_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    session_type: SessionType = SessionType.INITIAL_ASSESSMENT,
    status: ClinicalSessionStatus = ClinicalSessionStatus.COMPLETED,
) -> ClinicalSession:
    clinical_session = ClinicalSession(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        professional_id=professional_id,
        session_type=session_type,
        status=status,
        scheduled_at=None,
        started_at=None,
        ended_at=None,
        title=None,
        administrative_notes=None,
        reviewed_by=None,
        reviewed_at=None,
        created_by=created_by,
        updated_by=created_by,
        created_at=_now(),
        updated_at=_now(),
        schema_version=1,
        is_archived=False,
        archived_at=None,
    )
    await SqlAlchemyClinicalSessionRepository().add(session, clinical_session)
    await session.commit()
    return clinical_session


async def create_audio_recording(
    session: AsyncSession,
    clinical_session_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    *,
    status: ProcessingStatus = ProcessingStatus.READY,
    uploaded_at: datetime | None = None,
) -> AudioRecording:
    """`uploaded_at` explícito (no `server_default`) para poder simular
    audio antiguo en los tests de retención (Fase 7.2)."""
    row = AudioRecordingORM(
        id=uuid.uuid4(),
        clinical_session_id=clinical_session_id,
        status=status.value,
        storage_provider="local",
        storage_reference=f"audio/{uuid.uuid4().hex}.mp3",
        original_filename="consulta_ficticia.mp3",
        mime_type="audio/mpeg",
        extension="mp3",
        duration_seconds=30,
        size_bytes=1024,
        checksum=uuid.uuid4().hex,
        failure_reason=None,
        uploaded_by=uploaded_by,
        uploaded_at=uploaded_at or _now(),
        deleted_at=None,
    )
    session.add(row)
    await session.commit()
    return AudioRecording(
        id=row.id,
        clinical_session_id=row.clinical_session_id,
        status=ProcessingStatus(row.status),
        storage_provider=row.storage_provider,
        storage_reference=row.storage_reference,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        extension=row.extension,
        duration_seconds=row.duration_seconds,
        size_bytes=row.size_bytes,
        checksum=row.checksum,
        failure_reason=row.failure_reason,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at,
        deleted_at=row.deleted_at,
    )


async def create_integration_config(
    session: AsyncSession,
    integration_name: IntegrationName,
    updated_by: uuid.UUID,
    *,
    active_provider: str = "mock",
    enabled: bool = False,
) -> IntegrationConfig:
    row = IntegrationConfigORM(
        id=uuid.uuid4(),
        integration_name=integration_name.value,
        active_provider=active_provider,
        enabled=enabled,
        updated_by=updated_by,
    )
    session.add(row)
    await session.commit()
    return IntegrationConfig(
        id=row.id,
        integration_name=IntegrationName(row.integration_name),
        active_provider=row.active_provider,
        enabled=row.enabled,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


def dev_headers(user: User) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


def current_user_from(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        clinic_id=user.clinic_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
