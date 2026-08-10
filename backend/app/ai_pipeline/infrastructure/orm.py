"""Modelos ORM del AI Pipeline. Ver docs/data-model.md §2 y §10-11."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AIArtifactORM(Base):
    __tablename__ = "ai_artifacts"
    __table_args__ = (
        Index(
            "ux_ai_artifacts_session_type",
            "clinical_session_id",
            "artifact_type",
            unique=True,
        ),
        Index("ix_ai_artifacts_session", "clinical_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinical_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_sessions.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # FK diferida: la versión referenciada se inserta en la misma
    # operación que el propio AIArtifact (ver SqlAlchemyAIArtifactRepository.add_version).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_artifact_versions.id", use_alter=True), nullable=True
    )
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIArtifactVersionORM(Base):
    __tablename__ = "ai_artifact_versions"
    __table_args__ = (
        Index(
            "ux_ai_artifact_versions_artifact_number",
            "ai_artifact_id",
            "version_number",
            unique=True,
        ),
        Index(
            "ix_ai_artifact_versions_artifact_number_desc",
            "ai_artifact_id",
            "version_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ai_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_artifacts.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    generation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_generation_runs.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIGenerationRunORM(Base):
    __tablename__ = "ai_generation_runs"
    __table_args__ = (
        Index("ix_ai_generation_runs_pipeline_run", "ai_pipeline_run_id"),
        Index("ix_ai_generation_runs_session_type", "clinical_session_id", "artifact_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ai_pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_pipeline_runs.id"), nullable=False
    )
    clinical_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_sessions.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_artifacts.id"), nullable=True
    )
    resulting_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_templates.id"), nullable=True
    )
    prompt_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rendered_system_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    rendered_user_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AIPipelineRunORM(Base):
    __tablename__ = "ai_pipeline_runs"
    __table_args__ = (Index("ix_ai_pipeline_runs_session_status", "clinical_session_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinical_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_sessions.id"), nullable=False
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PromptTemplateORM(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index("ux_prompt_templates_name_version", "name", "version", unique=True),
        Index(
            "ux_prompt_templates_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    user_prompt_template: Mapped[str] = mapped_column(String, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
