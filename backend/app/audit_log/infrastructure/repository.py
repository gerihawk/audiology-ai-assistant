"""Repositorio de auditoría.

`add` solo hace `session.add(...)`: no comete la transacción. La
confirmación (commit/rollback) es responsabilidad del servicio que
escribe la entidad auditada, para garantizar que entidad y auditoría
viven o mueren juntas (ver PatientService).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.orm import AuditLogORM


class SqlAlchemyAuditLogRepository:
    async def add(self, session: AsyncSession, entry: AuditLogEntry) -> None:
        session.add(
            AuditLogORM(
                id=entry.id,
                clinic_id=entry.clinic_id,
                actor_user_id=entry.actor_user_id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                request_id=entry.request_id,
                audit_metadata=entry.metadata,
            )
        )
