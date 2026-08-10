"""Modelo ORM de AudioRecording. Ver docs/data-model.md §2."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AudioRecordingORM(Base):
    __tablename__ = "audio_recordings"
    __table_args__ = (
        Index("ix_audio_recordings_session", "clinical_session_id"),
        Index("ix_audio_recordings_session_status", "clinical_session_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinical_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
