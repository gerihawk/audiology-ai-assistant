"""Endpoints /api/v1/integrations — Fase 7.3."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.context import get_request_id
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_integration_config_service
from app.integrations.api.schemas import (
    IntegrationConfigListResponse,
    IntegrationConfigPatchRequest,
    IntegrationConfigResponse,
)
from app.integrations.domain.integration_config import IntegrationName
from app.integrations.service import IntegrationConfigPatchData, IntegrationConfigService

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=IntegrationConfigListResponse)
async def list_integrations(
    current_user: CurrentUser = Depends(get_current_user),
    service: IntegrationConfigService = Depends(get_integration_config_service),
) -> IntegrationConfigListResponse:
    items = await service.list_all(current_user)
    return IntegrationConfigListResponse(
        items=[IntegrationConfigResponse.model_validate(item) for item in items]
    )


@router.patch("/{integration_name}", response_model=IntegrationConfigResponse)
async def update_integration(
    integration_name: IntegrationName,
    payload: IntegrationConfigPatchRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: IntegrationConfigService = Depends(get_integration_config_service),
    request_id: str = Depends(get_request_id),
) -> IntegrationConfigResponse:
    updated = await service.update(
        current_user,
        integration_name,
        IntegrationConfigPatchData(
            enabled=payload.enabled, active_provider=payload.active_provider
        ),
        request_id,
    )
    return IntegrationConfigResponse.model_validate(updated)
