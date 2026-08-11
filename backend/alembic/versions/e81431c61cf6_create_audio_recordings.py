"""create_audio_recordings

Revision ID: e81431c61cf6
Revises: 65347bc82827
Create Date: 2026-08-10 13:16:23.211490

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e81431c61cf6"
down_revision: str | None = "65347bc82827"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_recordings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinical_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("storage_reference", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("failure_reason", sa.String(length=2000), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinical_session_id"], ["clinical_sessions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audio_recordings_session", "audio_recordings", ["clinical_session_id"])
    op.create_index(
        "ix_audio_recordings_session_status",
        "audio_recordings",
        ["clinical_session_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_audio_recordings_session_status", table_name="audio_recordings")
    op.drop_index("ix_audio_recordings_session", table_name="audio_recordings")
    op.drop_table("audio_recordings")
