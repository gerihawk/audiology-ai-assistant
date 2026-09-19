"""add current_period_started_at to clinics

Revision ID: 8b1e2f7c4a63
Revises: 44c526b3b6ea
Create Date: 2026-09-18 00:00:00.000001

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b1e2f7c4a63"
down_revision: str | None = "44c526b3b6ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column("current_period_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clinics", "current_period_started_at")
