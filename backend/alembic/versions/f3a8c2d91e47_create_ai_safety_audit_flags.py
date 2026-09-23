"""create ai_safety_audit_flags

Revision ID: f3a8c2d91e47
Revises: b7f4a9c1e358
Create Date: 2026-09-23 00:00:00.000000

Cierre del Paso 2 del hallazgo bloqueante del red team
(docs/security/red-team-app-2026-09-22.md §A1): capa de auditoría LLM
NO bloqueante sobre contenido que ya pasó el `SafetyValidator` determinista
(Paso 1). Tabla dedicada, no `audit_logs`: esa tabla exige `actor_user_id`
NOT NULL (acción humana atribuible) — esta es una señal generada por el
propio sistema, sin actor humano. `clinic_id` denormalizado (mismo patrón
de `audit_logs`) para poder acotar por clínica sin un JOIN a
`ai_artifact_versions`/`ai_artifacts`/`clinical_sessions`.

Deliberadamente NO se guarda el texto marcado completo — solo
`llm_reasoning` (motivo corto). Decisión explícita del usuario: esta tabla
nunca debe exponer contenido clínico completo a quien la revise
(`platform_admin`), solo la señal + el motivo breve.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8c2d91e47"
down_revision: str | None = "b7f4a9c1e358"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_safety_audit_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ai_artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("llm_flagged", sa.Boolean(), nullable=False),
        # Corto a propósito (ver docstring del módulo): nunca el texto
        # marcado completo, solo el motivo que dio el modelo.
        sa.Column("llm_reasoning", sa.String(length=500), nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ai_artifact_version_id"], ["ai_artifact_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_safety_audit_flags_clinic_created",
        "ai_safety_audit_flags",
        ["clinic_id", "created_at"],
    )
    op.create_index(
        "ix_ai_safety_audit_flags_version",
        "ai_safety_audit_flags",
        ["ai_artifact_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_safety_audit_flags_version", table_name="ai_safety_audit_flags")
    op.drop_index("ix_ai_safety_audit_flags_clinic_created", table_name="ai_safety_audit_flags")
    op.drop_table("ai_safety_audit_flags")
