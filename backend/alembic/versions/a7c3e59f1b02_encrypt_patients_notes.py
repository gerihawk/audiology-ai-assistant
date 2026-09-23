"""encrypt patients.notes (field-level encryption)

Revision ID: a7c3e59f1b02
Revises: f3a8c2d91e47
Create Date: 2026-09-23 00:00:00.000000

Cierre del hallazgo alto del red team (docs/security/red-team-app-2026-09-22.md
§B1): `patients.notes` pasa de `String(2000)` en claro a cifrado a nivel de
aplicación, mismo tipo (`EncryptedString`) que ya usan `display_name`/
`birth_year` desde la migración 729f6ad2ac76_encrypt_sensitive_columns.py
(18-sep-2026) — misma mecánica (`alter_column` a `Text`,
`postgresql_using`), mismo `downgrade()` simétrico.

Diferencia deliberada con 729f6ad2ac76: aquella migración NO re-cifra
ningún dato, solo cambia el tipo de columna — funcionó sin backfill porque
production tenía 0 filas en `patients` en ese momento exacto (verificado en
su propio docstring). Confirmado en Railway (2026-09-23, Gerard) que hoy
staging tiene 3 pacientes con 0 `notes` no vacíos y production tiene 0
pacientes — mismo escenario, sin backfill necesario. Pero a diferencia de
729f6ad2ac76, esta migración SÍ comprueba esa condición en tiempo de
`upgrade()`, en vez de asumirla: si alguien la aplica más adelante contra
un entorno que ya no está vacío (nueva clínica dada de alta entre hoy y el
despliegue), aborta ruidosamente con un mensaje claro en vez de dejar esos
datos ilegibles en silencio (`FieldEncryptionError` al leerlos después,
por no tener el prefijo `key_id:` que el descifrado espera).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e59f1b02"
down_revision: str | None = "f3a8c2d91e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    unsafe_row_count = connection.execute(
        sa.text("SELECT count(*) FROM patients WHERE notes IS NOT NULL AND notes != ''")
    ).scalar_one()
    if unsafe_row_count:
        raise RuntimeError(
            f"patients.notes tiene {unsafe_row_count} fila(s) con datos reales — esta "
            "migración solo es segura contra una tabla vacía de ese campo (mismo criterio "
            "que 729f6ad2ac76_encrypt_sensitive_columns.py). Hace falta un backfill que "
            "cifre esas filas con app/core/field_encryption.py antes de aplicar este "
            "alter_column, o los datos existentes quedarán ilegibles "
            "(FieldEncryptionError) en cuanto la aplicación intente descifrarlos."
        )
    op.alter_column(
        "patients",
        "notes",
        existing_type=sa.String(length=2000),
        type_=sa.Text(),
        postgresql_using="notes::text",
    )


def downgrade() -> None:
    op.alter_column(
        "patients",
        "notes",
        existing_type=sa.Text(),
        type_=sa.String(length=2000),
    )
