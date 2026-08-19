"""create_integration_configs

Revision ID: f3d8b1c4a920
Revises: a1c3f9d6b2e4
Create Date: 2026-08-18 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3d8b1c4a920"
down_revision: str | None = "a1c3f9d6b2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_name", sa.String(length=32), nullable=False),
        sa.Column("active_provider", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_configs_name", "integration_configs", ["integration_name"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_integration_configs_name", table_name="integration_configs")
    op.drop_table("integration_configs")
