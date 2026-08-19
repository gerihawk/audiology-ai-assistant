"""Esquemas Pydantic de la API de configuración de integraciones — Fase 7.3.

`IntegrationConfigPatchRequest` exige al menos un campo (`enabled` o
`active_provider`): un body vacío se rechaza con 422 nativo — mismo
criterio que otros esquemas de este proyecto donde el servidor nunca
acepta una operación sin efecto explícito en la petición.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.integrations.domain.integration_config import IntegrationName


class IntegrationConfigPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    active_provider: Literal["mock"] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.enabled is None and self.active_provider is None:
            raise ValueError("Debe indicarse 'enabled' y/o 'active_provider'.")
        return self


class IntegrationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_name: IntegrationName
    active_provider: str
    enabled: bool
    updated_by: uuid.UUID
    updated_at: datetime


class IntegrationConfigListResponse(BaseModel):
    items: list[IntegrationConfigResponse]
