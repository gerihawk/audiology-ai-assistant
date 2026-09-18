"""encrypt sensitive columns (field-level encryption)

Revision ID: 729f6ad2ac76
Revises: 999ee489bf3b
Create Date: 2026-09-18 00:00:00.000000

Cambia de tipo las columnas que a partir de ahora se cifran a nivel de
aplicación (ver app/core/field_encryption.py y
docs/privacy-and-security.md §4): todas pasan a `TEXT`, porque el
ciphertext es siempre más largo que el valor original y porque una
columna `JSONB` no puede contener el texto cifrado tal cual (deja de ser
JSON válido).

IMPORTANTE — esta migración NO re-cifra nada por sí sola, solo cambia el
tipo de columna. A fecha de esta migración, production tiene 0 filas en
`patients`/`ai_artifact_versions`/`ai_generation_runs` (verificado en vivo
contra la base real, ver docs/development-plan.md §Fase 11), así que no
hay ningún dato real que migrar. Si `staging`/`development` tienen datos
de prueba (seed) en estas tablas, el `USING` de más abajo los convierte a
texto PLANO, no cifrado — la aplicación no podrá descifrarlos (
`FieldEncryptionError`) porque no tienen el prefijo `key_id:` esperado.
**Tras aplicar esta migración en cualquier entorno con datos de prueba
previos, hay que vaciar esas tablas y volver a sembrarlas** (`make seed`
no trunca por sí solo, ver app/seed.py) antes de usar la aplicación —
son datos ficticios, sin ningún valor que conservar.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "729f6ad2ac76"
down_revision: str | None = "999ee489bf3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "patients",
        "display_name",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        postgresql_using="display_name::text",
    )
    op.alter_column(
        "patients",
        "birth_year",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        postgresql_using="birth_year::text",
    )
    op.alter_column(
        "ai_artifact_versions",
        "content",
        existing_type=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.Text(),
        postgresql_using="content::text",
    )
    op.alter_column(
        "ai_generation_runs",
        "rendered_system_prompt",
        existing_type=sa.String(),
        type_=sa.Text(),
    )
    op.alter_column(
        "ai_generation_runs",
        "rendered_user_prompt",
        existing_type=sa.String(),
        type_=sa.Text(),
    )
    op.alter_column(
        "ai_generation_runs",
        "raw_response",
        existing_type=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.Text(),
        postgresql_using="raw_response::text",
    )


def downgrade() -> None:
    # Simétrico a `upgrade()`: revertir el TIPO de columna, nunca intenta
    # "desencriptar" datos que ya se hayan cifrado con esta migración
    # aplicada — un downgrade real requeriría re-cifrar/descifrar primero
    # con app/core/field_encryption_cli.py y está fuera del alcance de lo
    # que Alembic puede automatizar.
    op.alter_column(
        "ai_generation_runs",
        "raw_response",
        existing_type=sa.Text(),
        type_=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="raw_response::jsonb",
    )
    op.alter_column(
        "ai_generation_runs",
        "rendered_user_prompt",
        existing_type=sa.Text(),
        type_=sa.String(),
    )
    op.alter_column(
        "ai_generation_runs",
        "rendered_system_prompt",
        existing_type=sa.Text(),
        type_=sa.String(),
    )
    op.alter_column(
        "ai_artifact_versions",
        "content",
        existing_type=sa.Text(),
        type_=sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="content::jsonb",
    )
    op.alter_column(
        "patients",
        "birth_year",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        postgresql_using="birth_year::integer",
    )
    op.alter_column(
        "patients",
        "display_name",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
    )
