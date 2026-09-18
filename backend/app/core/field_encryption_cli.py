"""Re-cifrado de columnas tras una rotación de `FIELD_ENCRYPTION_ACTIVE_KEY_ID`
(ver app/core/field_encryption.py). Invocación única por ejecución, mismo
patrón de bootstrap que `app.retention.cli`/`app.seed` — sin scheduler en
proceso, pensado para dispararse a mano tras cambiar la clave activa.

Procedimiento de rotación completo:

1. Generar una clave nueva: `python -c "import secrets, base64;
   print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
2. Añadirla a `FIELD_ENCRYPTION_KEYS` con un `key_id` nuevo, SIN quitar la
   clave anterior (formato `"id_viejo:clave_vieja,id_nuevo:clave_nueva"`),
   y desplegar ese cambio — en este punto ambas claves descifran, todavía
   se sigue cifrando con la vieja.
3. Cambiar `FIELD_ENCRYPTION_ACTIVE_KEY_ID` al `id_nuevo` y desplegar — a
   partir de aquí, todo lo que se escriba de nuevo usa la clave nueva,
   pero las filas ya existentes siguen cifradas con la vieja (siguen
   siendo legibles, la vieja sigue en `FIELD_ENCRYPTION_KEYS`).
4. Ejecutar este comando para re-cifrar con la clave nueva TODO lo que
   seguía con la vieja:
       docker compose run --rm backend python -m app.core.field_encryption_cli
5. Solo cuando este comando informe 0 filas pendientes en todas las
   tablas, es seguro retirar la clave vieja de `FIELD_ENCRYPTION_KEYS` y
   desplegar ese cambio final.

Nunca se salta el paso 4: retirar la clave vieja antes de re-cifrar deja
filas irrecuperables (`FieldEncryptionError`, ver `FieldCipher.decrypt`).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.ai_pipeline.infrastructure.orm import AIArtifactVersionORM, AIGenerationRunORM
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.db import get_session_factory
from app.core.field_encryption import get_field_cipher
from app.patients.infrastructure.orm import PatientORM

#: (modelo ORM, [nombres de columna cifrada]) — mismas columnas que
#: app/core/field_encryption.py aplica vía EncryptedString/EncryptedInt/
#: EncryptedJSON. Añadir aquí cualquier columna cifrada nueva en el futuro
#: para que la rotación la cubra automáticamente.
_ENCRYPTED_COLUMNS: list[tuple[type, list[str]]] = [
    (PatientORM, ["display_name", "birth_year"]),
    (
        AIArtifactVersionORM,
        ["content"],
    ),
    (
        AIGenerationRunORM,
        ["rendered_system_prompt", "rendered_user_prompt", "raw_response"],
    ),
]


async def _reencrypt_table(
    session: AsyncSession, model: type, columns: list[str]
) -> dict[str, int]:
    """Re-cifra en el sitio las columnas de `columns` para todas las filas
    de `model`. Se opera a través del ORM: leer `getattr(row, column)` ya
    descifra con `FieldCipher` (soporta cualquier key_id conocido).

    Reescribe TODAS las filas con contenido, no solo las que estuvieran
    cifradas con una clave distinta de la activa — determinar cuáles
    están "obsoletas" exigiría leer el `key_id` crudo antes de que el
    `TypeDecorator` lo descifre, lo que requiere SQL crudo o un `cast()`
    aparte; para una operación que se ejecuta a mano y rara vez (una
    rotación de claves, no algo que corra en cada deploy), el coste extra
    de re-cifrar filas que ya estaban al día es aceptable a cambio de
    mantener este comando simple.

    IMPORTANTE: `setattr(row, column, value)` con el MISMO valor Python
    que ya tenía la fila NO basta por sí solo — SQLAlchemy compara el
    nuevo valor contra el que cargó de la base de datos y, si son iguales
    en claro, no incluye esa columna en el `UPDATE` (nunca llega a
    invocar `process_bind_param`, así que nunca se re-cifra). Por eso
    cada asignación va seguida de `flag_modified()`, que fuerza a
    SQLAlchemy a tratar la columna como modificada sin importar si el
    valor en claro cambió."""
    result = await session.execute(select(model))
    rows = result.scalars().all()
    touched_rows = 0
    for row in rows:
        row_touched = False
        for column in columns:
            value = getattr(row, column)
            if value is None:
                continue
            setattr(row, column, value)
            flag_modified(row, column)
            row_touched = True
        if row_touched:
            touched_rows += 1
    await session.flush()
    return {"filas_recifradas": touched_rows, "filas_totales": len(rows)}


async def main(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, dict[str, int]]:
    session_factory = session_factory or get_session_factory()
    cipher = get_field_cipher()
    print(
        f"Clave activa: {cipher.active_key_id!r} — claves conocidas: {sorted(cipher.known_key_ids)}"
    )

    summary: dict[str, dict[str, int]] = {}
    async with session_factory() as session:
        for model, columns in _ENCRYPTED_COLUMNS:
            result = await _reencrypt_table(session, model, columns)
            summary[model.__tablename__] = result
            print(f"[{model.__tablename__}] {result}")
        await session.commit()
    return summary


if __name__ == "__main__":
    asyncio.run(main())
