"""add_token_version

Revision ID: c91e4d7a2b60
Revises: b58d1a4f0c93
Create Date: 2026-09-24 20:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c91e4d7a2b60"
down_revision: str | None = "b58d1a4f0c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("users", "platform_operators")


def upgrade() -> None:
    # Cierre del hallazgo bajo D1 del red team (docs/security/
    # red-team-app-2026-09-22.md): revocación de JWT en servidor. El JWT
    # lleva el valor vigente como claim `tv`; logout y reset de contraseña
    # lo incrementan. `server_default="0"` + tokens sin `tv` tratados como
    # `tv=0`: los tokens emitidos antes del deploy siguen siendo válidos.
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "token_version")
