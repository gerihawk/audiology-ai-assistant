"""add billing fields to clinics

Revision ID: 44c526b3b6ea
Revises: 729f6ad2ac76
Create Date: 2026-09-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "44c526b3b6ea"
down_revision: str | None = "729f6ad2ac76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column(
        "clinics", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
    )
    op.add_column("clinics", sa.Column("subscription_status", sa.String(length=32), nullable=True))
    op.add_column("clinics", sa.Column("plan", sa.String(length=32), nullable=True))
    op.add_column(
        "clinics",
        sa.Column(
            "sessions_used_this_period",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # Sin `unique`: el nivel Cadena/Empresa comparte el mismo
    # stripe_customer_id/stripe_subscription_id entre varias filas de
    # `clinics` (docs/fase-13-rfc.md §3.3) — solo índice para resolver
    # rápido desde el webhook.
    op.create_index(
        "ix_clinics_stripe_customer_id", "clinics", ["stripe_customer_id"], unique=False
    )
    op.create_index(
        "ix_clinics_stripe_subscription_id", "clinics", ["stripe_subscription_id"], unique=False
    )
    op.create_table(
        "stripe_webhook_events",
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
    op.drop_index("ix_clinics_stripe_subscription_id", table_name="clinics")
    op.drop_index("ix_clinics_stripe_customer_id", table_name="clinics")
    op.drop_column("clinics", "sessions_used_this_period")
    op.drop_column("clinics", "plan")
    op.drop_column("clinics", "subscription_status")
    op.drop_column("clinics", "stripe_subscription_id")
    op.drop_column("clinics", "stripe_customer_id")
