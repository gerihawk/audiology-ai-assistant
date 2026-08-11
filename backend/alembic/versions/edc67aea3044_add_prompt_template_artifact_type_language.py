"""add artifact_type/language to prompt_templates

Revision ID: edc67aea3044
Revises: 428ffeb65f71
Create Date: 2026-08-11 13:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "edc67aea3044"
down_revision: str | None = "428ffeb65f71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `prompt_templates` no tiene filas en ningún entorno todavía (Fase
    # 4.1: tabla creada, nunca sembrada — ver docs/development-plan.md
    # Fase 4.7/6.0.5) — columnas NOT NULL sin backfill.
    op.add_column(
        "prompt_templates", sa.Column("artifact_type", sa.String(length=32), nullable=False)
    )
    op.add_column("prompt_templates", sa.Column("language", sa.String(length=8), nullable=False))
    op.create_index(
        "ux_prompt_templates_artifact_type_language_active",
        "prompt_templates",
        ["artifact_type", "language"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_prompt_templates_artifact_type_language_active",
        table_name="prompt_templates",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_column("prompt_templates", "language")
    op.drop_column("prompt_templates", "artifact_type")
