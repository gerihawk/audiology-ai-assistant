"""Test de integración end-to-end de `app.onboarding.cleanup_cli.main()`
(Fase 12, hito 12.4) — mismo patrón que
`tests/test_retention_cli.py::test_main_purges_expired_audio_and_writes_summary_audit_entry`,
pero sin equivalente de `audit_log` (ver app/onboarding/cleanup_service.py
sobre por qué esta limpieza nunca escribe auditoría)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clinics.infrastructure.orm import ClinicORM
from app.core.config import get_settings
from app.onboarding.cleanup_cli import main
from app.users.domain.entities import Role
from tests.factories import create_clinic, create_user

_OLD = datetime.now(UTC) - timedelta(days=get_settings().unverified_clinic_ttl_days + 1)


async def test_main_purges_ghost_clinic_and_reports_it(
    test_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    ghost = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, ghost.id, role=Role.ADMIN, is_active=False)

    # `main()` recibe el session_factory de la BD de test aislada (no el
    # global de `app.core.db`, que apuntaría a la BD de desarrollo real) —
    # mismo motivo que en test_retention_cli.py.
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    result = await main(test_session_factory)

    assert result == {"purged_clinics": [str(ghost.id)]}
    assert (
        await db_session.execute(select(ClinicORM).where(ClinicORM.id == ghost.id))
    ).scalar_one_or_none() is None


async def test_main_with_nothing_to_purge_reports_empty_list(
    test_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    result = await main(test_session_factory)

    assert result == {"purged_clinics": []}
