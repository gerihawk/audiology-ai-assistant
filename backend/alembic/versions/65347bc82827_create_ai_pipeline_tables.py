"""create ai pipeline tables

Revision ID: 65347bc82827
Revises: 02946217c2ea
Create Date: 2026-08-10 11:11:17.738410

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "65347bc82827"
down_revision: str | None = "02946217c2ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CURRENT_VERSION_FK = "fk_ai_artifacts_current_version_id"


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("system_prompt", sa.String(), nullable=True),
        sa.Column("user_prompt_template", sa.String(), nullable=False),
        sa.Column(
            "variables_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("change_note", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_prompt_templates_name_active",
        "prompt_templates",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ux_prompt_templates_name_version", "prompt_templates", ["name", "version"], unique=True
    )

    # `current_version_id` referencia a `ai_artifact_versions`, que todavía
    # no existe (dependencia circular entre las dos tablas: cada versión
    # pertenece a un artefacto, y cada artefacto apunta a su versión
    # vigente). Se crea sin esa FK aquí y se añade con ALTER TABLE al
    # final, una vez existe `ai_artifact_versions` — ver
    # docs/data-model.md §10 y §11.
    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinical_session_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=2000), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["clinical_session_id"], ["clinical_sessions.id"]),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_artifacts_session", "ai_artifacts", ["clinical_session_id"])
    op.create_index(
        "ux_ai_artifacts_session_type",
        "ai_artifacts",
        ["clinical_session_id", "artifact_type"],
        unique=True,
    )

    op.create_table(
        "ai_pipeline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinical_session_id", sa.Uuid(), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["clinical_session_id"], ["clinical_sessions.id"]),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_pipeline_runs_session_status", "ai_pipeline_runs", ["clinical_session_id", "status"]
    )

    op.create_table(
        "ai_generation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ai_pipeline_run_id", sa.Uuid(), nullable=False),
        sa.Column("clinical_session_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("ai_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_version_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_template_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_template_version", sa.Integer(), nullable=True),
        sa.Column("input_token_count", sa.Integer(), nullable=True),
        sa.Column("output_token_count", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("rendered_system_prompt", sa.String(), nullable=True),
        sa.Column("rendered_user_prompt", sa.String(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=2000), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["ai_artifact_id"], ["ai_artifacts.id"]),
        sa.ForeignKeyConstraint(["ai_pipeline_run_id"], ["ai_pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["clinical_session_id"], ["clinical_sessions.id"]),
        sa.ForeignKeyConstraint(["prompt_template_id"], ["prompt_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_generation_runs_pipeline_run", "ai_generation_runs", ["ai_pipeline_run_id"]
    )
    op.create_index(
        "ix_ai_generation_runs_session_type",
        "ai_generation_runs",
        ["clinical_session_id", "artifact_type"],
    )

    op.create_table(
        "ai_artifact_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ai_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("source_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("change_note", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ai_artifact_id"], ["ai_artifacts.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["generation_run_id"], ["ai_generation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_artifact_versions_artifact_number_desc",
        "ai_artifact_versions",
        ["ai_artifact_id", "version_number"],
    )
    op.create_index(
        "ux_ai_artifact_versions_artifact_number",
        "ai_artifact_versions",
        ["ai_artifact_id", "version_number"],
        unique=True,
    )

    # Cierra la dependencia circular ahora que `ai_artifact_versions` existe.
    op.create_foreign_key(
        _CURRENT_VERSION_FK,
        "ai_artifacts",
        "ai_artifact_versions",
        ["current_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(_CURRENT_VERSION_FK, "ai_artifacts", type_="foreignkey")

    op.drop_index("ux_ai_artifact_versions_artifact_number", table_name="ai_artifact_versions")
    op.drop_index(
        "ix_ai_artifact_versions_artifact_number_desc", table_name="ai_artifact_versions"
    )
    op.drop_table("ai_artifact_versions")

    op.drop_index("ix_ai_generation_runs_session_type", table_name="ai_generation_runs")
    op.drop_index("ix_ai_generation_runs_pipeline_run", table_name="ai_generation_runs")
    op.drop_table("ai_generation_runs")

    op.drop_index("ix_ai_pipeline_runs_session_status", table_name="ai_pipeline_runs")
    op.drop_table("ai_pipeline_runs")

    op.drop_index("ux_ai_artifacts_session_type", table_name="ai_artifacts")
    op.drop_index("ix_ai_artifacts_session", table_name="ai_artifacts")
    op.drop_table("ai_artifacts")

    op.drop_index("ux_prompt_templates_name_version", table_name="prompt_templates")
    op.drop_index(
        "ux_prompt_templates_name_active",
        table_name="prompt_templates",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("prompt_templates")
