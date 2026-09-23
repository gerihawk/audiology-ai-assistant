"""patient_identity_purge_and_consents_fk

Revision ID: b58d1a4f0c93
Revises: a7c3e59f1b02
Create Date: 2026-09-23 20:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b58d1a4f0c93"
down_revision: str | None = "a7c3e59f1b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSENTS_SESSION_FK = "consents_clinical_session_id_fkey"


def upgrade() -> None:
    # Cierre del hallazgo medio del red team (docs/security/
    # red-team-app-2026-09-22.md): purge_patient_clinical_data() anonimiza
    # ahora la identidad del paciente in-place — esta columna distingue
    # auditablemente "se archivó" (reversible) de "se anonimizó por RGPD"
    # (irreversible). Ver PatientORM.identity_purged_at.
    op.add_column(
        "patients", sa.Column("identity_purged_at", sa.DateTime(timezone=True), nullable=True)
    )

    # `consents.clinical_session_id` no tenía `ondelete` definido: un
    # DELETE físico de `clinical_sessions` durante la purga fallaba por
    # violación de FK si el paciente tenía un consentimiento asociado a esa
    # sesión, y el `except Exception` genérico del servicio lo tragaba como
    # rollback silencioso. `consents` nunca se purga (prueba legal de
    # consentimiento); solo pierde la referencia a la sesión ya borrada.
    op.drop_constraint(_CONSENTS_SESSION_FK, "consents", type_="foreignkey")
    op.create_foreign_key(
        _CONSENTS_SESSION_FK,
        "consents",
        "clinical_sessions",
        ["clinical_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSENTS_SESSION_FK, "consents", type_="foreignkey")
    op.create_foreign_key(
        _CONSENTS_SESSION_FK, "consents", "clinical_sessions", ["clinical_session_id"], ["id"]
    )
    op.drop_column("patients", "identity_purged_at")
