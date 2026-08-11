"""create_consents

Revision ID: 428ffeb65f71
Revises: e81431c61cf6
Create Date: 2026-08-11 07:38:41.667479

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "428ffeb65f71"
down_revision: str | None = "e81431c61cf6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("clinical_session_id", sa.Uuid(), nullable=True),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=True),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["clinical_session_id"], ["clinical_sessions.id"]),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consents_patient_type", "consents", ["patient_id", "consent_type"])
    op.create_index("ix_consents_clinic", "consents", ["clinic_id"])


def downgrade() -> None:
    op.drop_index("ix_consents_clinic", table_name="consents")
    op.drop_index("ix_consents_patient_type", table_name="consents")
    op.drop_table("consents")
