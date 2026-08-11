"""Modelo ORM de Consent (tabla consents). Ver docs/data-model.md §2."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConsentORM(Base):
    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_patient_type", "patient_id", "consent_type"),
        Index("ix_consents_clinic", "clinic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinics.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False)
    clinical_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinical_sessions.id"), nullable=True
    )
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
