"""Modelo ORM de AuditLogEntry (tabla audit_logs).

El atributo Python no puede llamarse `metadata` (reservado por
DeclarativeBase.metadata); se mapea como `audit_metadata` a la columna
`metadata`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLogORM(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor", "actor_user_id"),
        Index("ix_audit_logs_clinic_timestamp", "clinic_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinics.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
