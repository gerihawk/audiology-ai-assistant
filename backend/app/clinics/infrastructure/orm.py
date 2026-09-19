"""Modelo ORM de Clinic."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClinicORM(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # --- Facturación / Stripe (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md §5 ---
    # Sin `unique`: el nivel Cadena/Empresa comparte el mismo
    # `stripe_customer_id`/`stripe_subscription_id` entre varias filas de
    # `Clinic` (§3.3) — `index` sin más, para resolver rápido "qué
    # clínica(s) corresponden a este customer/subscription" desde el
    # webhook.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sessions_used_this_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Fase 13, hito 13.2 — ver docstring de Clinic.current_period_started_at.
    current_period_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
