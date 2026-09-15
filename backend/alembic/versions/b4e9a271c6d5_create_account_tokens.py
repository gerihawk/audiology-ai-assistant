"""create account_tokens

Revision ID: b4e9a271c6d5
Revises: 7c2e4f5a8b31
Create Date: 2026-09-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e9a271c6d5"
down_revision: str | None = "7c2e4f5a8b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"], unique=False)
    op.create_index("ix_account_tokens_token_hash", "account_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_account_tokens_user_purpose", "account_tokens", ["user_id", "purpose"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_account_tokens_user_purpose", table_name="account_tokens")
    op.drop_index("ix_account_tokens_token_hash", table_name="account_tokens")
    op.drop_index("ix_account_tokens_user_id", table_name="account_tokens")
    op.drop_table("account_tokens")
