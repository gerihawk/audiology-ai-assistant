"""Tests de integración de `POST /api/v1/onboarding/system-cleanup` (Fase
12, hito 12.4) — mismo patrón que la sección `/system-purge` de
tests/test_retention_api.py: auth por secreto de cron (nunca
`get_current_user`) y purga cross-clínica real contra la BD de test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.main import app as fastapi_app
from app.users.domain.entities import Role
from tests.factories import create_clinic, create_user

_OLD = datetime.now(UTC) - timedelta(days=get_settings().unverified_clinic_ttl_days + 1)


async def test_system_cleanup_without_header_is_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/onboarding/system-cleanup")
    assert response.status_code == 401


async def test_system_cleanup_with_wrong_secret_is_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/onboarding/system-cleanup",
        headers={"X-Onboarding-Cleanup-Cron-Secret": "secreto-incorrecto"},
    )
    assert response.status_code == 401


async def test_system_cleanup_with_correct_secret_purges_ghost_clinics_cross_clinic(
    api_client: AsyncClient,
    test_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    ghost = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, ghost.id, role=Role.ADMIN, is_active=False)
    verified = await create_clinic(db_session, created_at=_OLD)
    await create_user(db_session, verified.id, role=Role.ADMIN, is_active=True)

    # Mismo motivo que test_retention_api.py::
    # test_system_purge_with_correct_secret_purges_expired_audio_cross_clinic:
    # el endpoint usa por defecto el session_factory global de
    # `get_settings().database_url`, distinto de la BD de test aislada.
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    fastapi_app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    try:
        response = await api_client.post(
            "/api/v1/onboarding/system-cleanup",
            headers={
                "X-Onboarding-Cleanup-Cron-Secret": get_settings().onboarding_cleanup_cron_secret
            },
        )
    finally:
        fastapi_app.dependency_overrides.pop(get_session_factory, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["purged_clinics"] == [str(ghost.id)]
