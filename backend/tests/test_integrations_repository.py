"""Repositorio de configuración de integraciones
(`SqlAlchemyIntegrationConfigRepository`) — Fase 7.3
(docs/development-plan.md)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.domain.integration_config import IntegrationName
from app.integrations.infrastructure.repository import SqlAlchemyIntegrationConfigRepository
from tests.factories import ClinicWithUsers, create_integration_config


async def test_get_by_name_returns_none_when_not_seeded(db_session: AsyncSession):
    result = await SqlAlchemyIntegrationConfigRepository().get_by_name(
        db_session, IntegrationName.CALENDAR
    )
    assert result is None


async def test_get_by_name_returns_existing_row(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    created = await create_integration_config(
        db_session, IntegrationName.CALENDAR, clinic_with_users.admin.id
    )

    result = await SqlAlchemyIntegrationConfigRepository().get_by_name(
        db_session, IntegrationName.CALENDAR
    )

    assert result is not None
    assert result.id == created.id
    assert result.active_provider == "mock"
    assert result.enabled is False


async def test_list_all_returns_every_row_ordered_by_name(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    await create_integration_config(
        db_session, IntegrationName.PATIENT_RECORD, clinic_with_users.admin.id
    )
    await create_integration_config(
        db_session, IntegrationName.CALENDAR, clinic_with_users.admin.id
    )

    result = await SqlAlchemyIntegrationConfigRepository().list_all(db_session)

    assert [item.integration_name for item in result] == [
        IntegrationName.CALENDAR,
        IntegrationName.PATIENT_RECORD,
    ]


async def test_update_fields_applies_partial_patch(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    await create_integration_config(
        db_session, IntegrationName.CALENDAR, clinic_with_users.admin.id
    )

    updated = await SqlAlchemyIntegrationConfigRepository().update_fields(
        db_session,
        IntegrationName.CALENDAR,
        {"enabled": True, "updated_by": clinic_with_users.admin.id},
    )

    assert updated is not None
    assert updated.enabled is True
    assert updated.active_provider == "mock"


async def test_update_fields_returns_none_when_not_seeded(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    result = await SqlAlchemyIntegrationConfigRepository().update_fields(
        db_session,
        IntegrationName.CALENDAR,
        {"enabled": True, "updated_by": clinic_with_users.admin.id},
    )
    assert result is None
