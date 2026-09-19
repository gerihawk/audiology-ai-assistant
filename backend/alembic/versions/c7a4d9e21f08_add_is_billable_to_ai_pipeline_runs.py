"""add is_billable to ai_pipeline_runs

Revision ID: c7a4d9e21f08
Revises: 8b1e2f7c4a63
Create Date: 2026-09-18 00:00:00.000002

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a4d9e21f08"
down_revision: str | None = "8b1e2f7c4a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_pipeline_runs",
        sa.Column("is_billable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ai_pipeline_runs", "is_billable")
