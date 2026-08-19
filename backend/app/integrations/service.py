"""IntegrationConfigService: autoriza → valida `integration_name` conocido →
aplica patch parcial → audita `integration_config.updated` → commit. Fase
7.3 (docs/development-plan.md). Mismo patrón transaccional que
`ConsentService`/`RetentionCleanupService`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.core.authorization import IntegrationConfigAction, authorize_integration_config_action
from app.core.current_user import CurrentUser
from app.core.exceptions import NotFoundError
from app.integrations.domain.integration_config import IntegrationConfig, IntegrationName
from app.integrations.infrastructure.repository import SqlAlchemyIntegrationConfigRepository


@dataclass(slots=True)
class IntegrationConfigPatchData:
    enabled: bool | None
    active_provider: str | None


class IntegrationConfigService:
    def __init__(
        self,
        session: AsyncSession,
        repository: SqlAlchemyIntegrationConfigRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._configs = repository or SqlAlchemyIntegrationConfigRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def list_all(self, current_user: CurrentUser) -> list[IntegrationConfig]:
        authorize_integration_config_action(current_user, IntegrationConfigAction.READ)
        return await self._configs.list_all(self._session)

    async def update(
        self,
        current_user: CurrentUser,
        integration_name: IntegrationName,
        data: IntegrationConfigPatchData,
        request_id: str,
    ) -> IntegrationConfig:
        authorize_integration_config_action(current_user, IntegrationConfigAction.UPDATE)
        existing = await self._configs.get_by_name(self._session, integration_name)
        if existing is None:
            raise NotFoundError("Integración no encontrada.")

        changed_fields: list[str] = []
        values: dict[str, object] = {}
        if data.enabled is not None and data.enabled != existing.enabled:
            values["enabled"] = data.enabled
            changed_fields.append("enabled")
        if data.active_provider is not None and data.active_provider != existing.active_provider:
            values["active_provider"] = data.active_provider
            changed_fields.append("active_provider")

        if not changed_fields:
            # No-op idempotente: mismo criterio que `patients.archive`/
            # `restore` — sin cambios reales, sin nueva entrada de auditoría.
            return existing

        values["updated_by"] = current_user.id
        try:
            updated = await self._configs.update_fields(self._session, integration_name, values)
            assert updated is not None  # ya comprobado con get_by_name arriba
            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="integration_config.updated",
                    entity_type="integration_config",
                    entity_id=updated.id,
                    request_id=request_id,
                    metadata={
                        "integration_name": integration_name.value,
                        "changed_fields": changed_fields,
                    },
                ),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated
