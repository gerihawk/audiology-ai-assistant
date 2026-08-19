"""Tests de integración de /api/v1/integrations — Fase 7.3
(docs/development-plan.md). Permisos (solo admin), validación de PATCH
(al menos un campo, `active_provider` restringido a `mock`), idempotencia
y auditoría (`integration_config.updated`)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.infrastructure.orm import AuditLogORM
from app.integrations.domain.integration_config import IntegrationConfig, IntegrationName
from tests.factories import ClinicWithUsers, create_integration_config, dev_headers


@pytest_asyncio.fixture
async def patient_record_config(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> IntegrationConfig:
    return await create_integration_config(
        db_session, IntegrationName.PATIENT_RECORD, clinic_with_users.admin.id
    )


# --- Permisos: solo admin, ni siquiera audiologist ------------------------


async def test_admin_can_list_integrations(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.get(
        "/api/v1/integrations", headers=dev_headers(clinic_with_users.admin)
    )
    assert response.status_code == 200, response.text
    names = {item["integration_name"] for item in response.json()["items"]}
    assert "patient_record" in names


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_list_integrations_forbidden_for_non_admin(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, role_attr: str
):
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.get("/api/v1/integrations", headers=dev_headers(user))
    assert response.status_code == 403


@pytest.mark.parametrize("role_attr", ["audiologist", "viewer"])
async def test_patch_integration_forbidden_for_non_admin(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
    role_attr: str,
):
    user = getattr(clinic_with_users, role_attr)
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={"enabled": True},
        headers=dev_headers(user),
    )
    assert response.status_code == 403


# --- Validación del PATCH --------------------------------------------------


async def test_patch_integration_rejects_empty_body(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_patch_integration_rejects_non_mock_provider(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={"active_provider": "noah_real"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_patch_integration_rejects_unknown_field(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={"enabled": True, "unexpected": "x"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_patch_unknown_integration_name_is_422(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.patch(
        "/api/v1/integrations/transcription",
        json={"enabled": True},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 422


async def test_patch_unseeded_integration_is_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.patch(
        "/api/v1/integrations/calendar",
        json={"enabled": True},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


# --- PATCH: aplica cambios, idempotencia, auditoría ------------------------


async def test_patch_integration_updates_enabled_and_audits(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={"enabled": True},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["active_provider"] == "mock"
    assert body["updated_by"] == str(clinic_with_users.admin.id)

    entries = (
        (
            await db_session.execute(
                select(AuditLogORM).where(AuditLogORM.action == "integration_config.updated")
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1
    assert entries[0].audit_metadata["integration_name"] == "patient_record"
    assert entries[0].audit_metadata["changed_fields"] == ["enabled"]


async def test_patch_integration_with_no_actual_change_is_noop(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient_record_config: IntegrationConfig,
):
    response = await api_client.patch(
        "/api/v1/integrations/patient_record",
        json={"active_provider": "mock"},
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 200, response.text

    entries = (
        (
            await db_session.execute(
                select(AuditLogORM).where(AuditLogORM.action == "integration_config.updated")
            )
        )
        .scalars()
        .all()
    )
    assert entries == []
