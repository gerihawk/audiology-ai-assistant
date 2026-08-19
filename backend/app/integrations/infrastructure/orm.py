"""Modelo ORM de IntegrationConfig (tabla integration_configs).

Ver docs/data-model.md §2. Sin `clinic_id`: configuración global de
aplicación (decisión cerrada, Fase 7.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IntegrationConfigORM(Base):
    __tablename__ = "integration_configs"
    __table_args__ = (Index("ix_integration_configs_name", "integration_name", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    integration_name: Mapped[str] = mapped_column(String(32), nullable=False)
    active_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
