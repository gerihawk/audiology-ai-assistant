"""add negotiated_included_sessions to clinics

Revision ID: b7f4a9c1e358
Revises: d4f7c8e2a915
Create Date: 2026-09-21 00:00:00.000000

Ampliación del hito 13.2/13.3 (docs/fase-13-rfc.md §3.3), a raíz de la
auditoría entre fases del 2026-09-21: el nivel Cadena/Empresa se
factura por volumen negociado caso a caso, así que el tope de sesiones
incluidas no puede vivir en la tabla global `PLAN_INCLUDED_SESSIONS`
(app/billing/domain/plans.py) como el resto de niveles — cada `Clinic`
de este nivel necesita su propio tope, fijado a mano por Gerard al
negociar el contrato (panel de operador de la plataforma,
`app.platform_admin`). Nullable: `None` mientras esa clínica no tenga
un tope negociado todavía, mismo comportamiento que hasta ahora (sin
techo de seguridad, nunca bloquea por uso).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f4a9c1e358"
down_revision: str | None = "d4f7c8e2a915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column("negotiated_included_sessions", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clinics", "negotiated_included_sessions")
