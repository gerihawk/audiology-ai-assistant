"""Implementación SQLAlchemy del repositorio de IntegrationConfig."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.domain.integration_config import IntegrationConfig, IntegrationName
from app.integrations.infrastructure.orm import IntegrationConfigORM


def _to_domain(row: IntegrationConfigORM) -> IntegrationConfig:
    return IntegrationConfig(
        id=row.id,
        integration_name=IntegrationName(row.integration_name),
        active_provider=row.active_provider,
        enabled=row.enabled,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class SqlAlchemyIntegrationConfigRepository:
    async def add(self, session: AsyncSession, config: IntegrationConfig) -> IntegrationConfig:
        row = IntegrationConfigORM(
            id=config.id,
            integration_name=config.integration_name.value,
            active_provider=config.active_provider,
            enabled=config.enabled,
            updated_by=config.updated_by,
        )
        session.add(row)
        await session.flush()
        return _to_domain(row)

    async def list_all(self, session: AsyncSession) -> list[IntegrationConfig]:
        result = await session.execute(
            select(IntegrationConfigORM).order_by(IntegrationConfigORM.integration_name)
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def get_by_name(
        self, session: AsyncSession, integration_name: IntegrationName
    ) -> IntegrationConfig | None:
        result = await session.execute(
            select(IntegrationConfigORM).where(
                IntegrationConfigORM.integration_name == integration_name.value
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def update_fields(
        self, session: AsyncSession, integration_name: IntegrationName, values: dict[str, Any]
    ) -> IntegrationConfig | None:
        result = await session.execute(
            select(IntegrationConfigORM).where(
                IntegrationConfigORM.integration_name == integration_name.value
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            setattr(row, key, value)
        await session.flush()
        # `updated_at` (onupdate=func.now()) queda "expired" tras el flush de
        # un UPDATE — sin este refresh explícito, leerlo en _to_domain()
        # dispara una carga perezosa síncrona fuera de contexto async
        # (MissingGreenlet).
        await session.refresh(row)
        return _to_domain(row)
