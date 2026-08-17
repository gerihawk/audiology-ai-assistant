"""add baseline_artifact_id/baseline_version_id to ai_artifacts

Revision ID: a1c3f9d6b2e4
Revises: edc67aea3044
Create Date: 2026-08-14 16:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3f9d6b2e4"
down_revision: str | None = "edc67aea3044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_ARTIFACT_FK = "fk_ai_artifacts_baseline_artifact_id"
_BASELINE_VERSION_FK = "fk_ai_artifacts_baseline_version_id"


def upgrade() -> None:
    # Hito 6.5.3 (RFC técnico de 6.5 §1/§11): identidad del baseline exacto
    # de una propuesta de AnamnesisUpdateStep — NULL para todo artefacto
    # existente y para cualquier artefacto que no sea una propuesta de
    # actualización. Sin backfill: todo lo preexistente queda
    # correctamente NULL (nada preexistente es una propuesta).
    op.add_column("ai_artifacts", sa.Column("baseline_artifact_id", sa.Uuid(), nullable=True))
    op.add_column("ai_artifacts", sa.Column("baseline_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        _BASELINE_ARTIFACT_FK, "ai_artifacts", "ai_artifacts", ["baseline_artifact_id"], ["id"]
    )
    op.create_foreign_key(
        _BASELINE_VERSION_FK,
        "ai_artifacts",
        "ai_artifact_versions",
        ["baseline_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(_BASELINE_VERSION_FK, "ai_artifacts", type_="foreignkey")
    op.drop_constraint(_BASELINE_ARTIFACT_FK, "ai_artifacts", type_="foreignkey")
    op.drop_column("ai_artifacts", "baseline_version_id")
    op.drop_column("ai_artifacts", "baseline_artifact_id")
