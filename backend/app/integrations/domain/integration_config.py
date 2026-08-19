"""Entidad IntegrationConfig y su enum. Sin dependencias de SQLAlchemy.

Ver docs/data-model.md §2 (`integration_configs`) y docs/development-plan.md
Fase 7.3. Cubre únicamente `patient_record`/`calendar` — `transcription`/
`language_model` siguen resueltos por `Settings` (variables de entorno), no
por esta tabla (ver nota de corrección en docs/data-model.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class IntegrationName(StrEnum):
    PATIENT_RECORD = "patient_record"
    CALENDAR = "calendar"


@dataclass(slots=True)
class IntegrationConfig:
    id: uuid.UUID
    integration_name: IntegrationName
    active_provider: str
    enabled: bool
    updated_by: uuid.UUID
    updated_at: datetime


class IntegrationConfigRepository(Protocol):
    async def add(self, session: AsyncSession, config: IntegrationConfig) -> IntegrationConfig: ...

    async def list_all(self, session: AsyncSession) -> list[IntegrationConfig]: ...

    async def get_by_name(
        self, session: AsyncSession, integration_name: IntegrationName
    ) -> IntegrationConfig | None: ...

    async def update_fields(
        self, session: AsyncSession, integration_name: IntegrationName, values: dict[str, Any]
    ) -> IntegrationConfig | None: ...
