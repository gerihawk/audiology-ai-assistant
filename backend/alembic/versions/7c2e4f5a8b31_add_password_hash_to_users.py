"""add password_hash to users

Revision ID: 7c2e4f5a8b31
Revises: f3d8b1c4a920
Create Date: 2026-08-19 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c2e4f5a8b31"
down_revision: str | None = "f3d8b1c4a920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: los usuarios existentes (seed anterior a la Fase 9) no
    # tienen contraseña todavía — sin backfill, `AuthService.login` trata
    # `password_hash IS NULL` como "nunca autentica con éxito".
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
