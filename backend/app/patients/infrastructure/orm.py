"""Modelo ORM de Patient."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PatientORM(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("clinic_id", "internal_code", name="uq_patients_clinic_internal_code"),
        Index("ix_patients_clinic_archived", "clinic_id", "is_archived"),
        Index("ix_patients_clinic_created_at", "clinic_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id"), nullable=False, index=True
    )
    internal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_language: Mapped[str] = mapped_column(
        String(5), nullable=False, default="es", server_default="es"
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
