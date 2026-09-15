"""Tests de integración de `UnverifiedClinicCleanupService` (Fase 12,
hito 12.4): criterio de selección (`created_at` + ausencia de usuario
activo) y borrado en cascada (account_tokens -> users -> clinics), vía la
BD de test real (sin `ondelete=CASCADE` en el esquema, ver
app/onboarding/cleanup_service.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.infrastructure.orm import ClinicORM
from app.core.config import get_settings
from app.onboarding.cleanup_service import UnverifiedClinicCleanupService
from app.onboarding.domain.entities import AccountToken, AccountTokenPurpose
from app.onboarding.infrastructure.repository import SqlAlchemyAccountTokenRepository
from app.users.domain.entities import Role
from app.users.infrastructure.orm import UserORM
from tests.factories import create_clinic, create_user

_TTL_DAYS = get_settings().unverified_clinic_ttl_days
_OLD = datetime.now(UTC) - timedelta(days=_TTL_DAYS + 1)
_RECENT = datetime.now(UTC) - timedelta(days=1)


async def _add_verification_token(session: AsyncSession, user_id: uuid.UUID) -> AccountToken:
    token = AccountToken(
        id=uuid.uuid4(),
        user_id=user_id,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        used_at=None,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyAccountTokenRepository().add(session, token)
    await session.commit()
    return token


# --- find_unverified: criterio de selección -------------------------------


async def test_finds_old_clinic_without_active_admin(db_session: AsyncSession) -> None:
    clinic = await create_clinic(db_session, created_at=_OLD)
    admin = await create_user(db_session, clinic.id, role=Role.ADMIN, is_active=False)
    await _add_verification_token(db_session, admin.id)

    found = await UnverifiedClinicCleanupService(db_session).find_unverified()

    assert [c.id for c in found] == [clinic.id]


async def test_excludes_old_clinic_with_active_admin(db_session: AsyncSession) -> None:
    clinic = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, clinic.id, role=Role.ADMIN, is_active=True)

    found = await UnverifiedClinicCleanupService(db_session).find_unverified()

    assert clinic.id not in [c.id for c in found]


async def test_excludes_recent_clinic_without_active_admin(db_session: AsyncSession) -> None:
    """Todavía dentro del plazo de gracia — el admin puede verificar el
    email en cualquier momento antes de que expire."""
    clinic = await create_clinic(db_session, created_at=_RECENT)
    await create_user(db_session, clinic.id, role=Role.ADMIN, is_active=False)

    found = await UnverifiedClinicCleanupService(db_session).find_unverified()

    assert clinic.id not in [c.id for c in found]


async def test_excludes_old_clinic_with_no_users_at_all(db_session: AsyncSession) -> None:
    """Caso borde: clínica creada pero sin ningún usuario todavía (no
    debería poder ocurrir vía `POST /clinics/signup`, que crea siempre el
    admin en la misma transacción, pero `~exists()` la trataría igual como
    candidata — se cubre explícitamente)."""
    clinic = await create_clinic(db_session, created_at=_OLD)

    found = await UnverifiedClinicCleanupService(db_session).find_unverified()

    assert [c.id for c in found] == [clinic.id]


# --- purge: borrado físico en cascada, sin audit_log ----------------------


async def test_purge_deletes_clinic_users_and_tokens(db_session: AsyncSession) -> None:
    clinic = await create_clinic(db_session, created_at=_OLD)
    admin = await create_user(db_session, clinic.id, role=Role.ADMIN, is_active=False)
    token = await _add_verification_token(db_session, admin.id)

    purged = await UnverifiedClinicCleanupService(db_session).purge()

    assert [c.id for c in purged] == [clinic.id]

    assert (
        await db_session.execute(select(ClinicORM).where(ClinicORM.id == clinic.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(UserORM).where(UserORM.id == admin.id))
    ).scalar_one_or_none() is None
    assert (
        await SqlAlchemyAccountTokenRepository().get_by_hash(
            db_session, token.token_hash, AccountTokenPurpose.EMAIL_VERIFICATION
        )
    ) is None


async def test_purge_leaves_verified_clinics_untouched(db_session: AsyncSession) -> None:
    old_verified = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, old_verified.id, role=Role.ADMIN, is_active=True)

    purged = await UnverifiedClinicCleanupService(db_session).purge()

    assert purged == []
    assert (
        await db_session.execute(select(ClinicORM).where(ClinicORM.id == old_verified.id))
    ).scalar_one_or_none() is not None


async def test_purge_with_nothing_to_purge_returns_empty_list(db_session: AsyncSession) -> None:
    assert await UnverifiedClinicCleanupService(db_session).purge() == []


async def test_purge_is_idempotent(db_session: AsyncSession) -> None:
    clinic = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, clinic.id, role=Role.ADMIN, is_active=False)
    service = UnverifiedClinicCleanupService(db_session)

    first = await service.purge()
    second = await service.purge()

    assert [c.id for c in first] == [clinic.id]
    assert second == []
