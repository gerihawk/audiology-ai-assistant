"""create platform_operators

Revision ID: d4f7c8e2a915
Revises: c7a4d9e21f08
Create Date: 2026-09-20 00:00:00.000000

Fase 14 — panel de gestión de clínicas para el operador de la plataforma
(Gerard). Tabla completamente aparte de `users`: sin `clinic_id`, sin FK a
`clinics`, sin relación con `Role`/`CurrentUser`. Deliberado (ver
docs/development-plan.md Fase 14): un `platform_operator` no es un usuario
de ninguna clínica, así que reutilizar `users` habría obligado a hacer
`clinic_id` nullable en todo el sistema de autorización existente
(`app/core/authorization.py`, cada `authorize_*`), que hoy asume en todas
partes que todo usuario pertenece a exactamente una clínica. Con una tabla
propia, ese invariante no se toca en ningún sitio.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f7c8e2a915"
down_revision: str | None = "c7a4d9e21f08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_operators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        # Nullable por el mismo motivo que `users.password_hash`: permite
        # crear la fila (p. ej. desde un futuro CLI de invitación) antes de
        # que la persona fije su propia contraseña. `PlatformAdminAuthService`
        # trata `password_hash IS NULL` igual que `AuthService`: nunca
        # autentica con éxito.
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_operators_email", "platform_operators", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_platform_operators_email", table_name="platform_operators")
    op.drop_table("platform_operators")
