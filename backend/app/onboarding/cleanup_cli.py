"""Comando de limpieza de clínicas fantasma (nunca verificadas) — Fase
12, hito 12.4. Invocación única por ejecución, mismo patrón de bootstrap
que `app.retention.cli`/`app.seed`: sin scheduler en proceso, pensado
para que un cron externo (host, sidecar de docker-compose, o el cron
dedicado de Railway en el entorno de despliegue real) lo dispare
periódicamente.

A diferencia de `app.retention.cli.main()`, no hay ningún bucle por
clínica ni ningún admin que resolver como actor:
`UnverifiedClinicCleanupService` ya opera cross-clínica de por sí (ver su
docstring sobre por qué no hay `CurrentUser` posible) — este módulo solo
hace de bootstrap de sesión + impresión por stdout.

Uso local (docker-compose, mismo volumen/BD que el backend):
    docker compose run --rm backend python -m app.onboarding.cleanup_cli

En el entorno de despliegue real, un cron externo no tiene acceso a ese
contenedor: dispara en su lugar `POST /api/v1/onboarding/system-cleanup`
(ver app/onboarding/api/router.py), que llama a `main()` desde dentro del
propio proceso del backend — mismo patrón que
`POST /api/v1/retention/system-purge` (app/retention/cli.py).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.db import get_session_factory
from app.onboarding.cleanup_service import UnverifiedClinicCleanupService


async def main(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, list[str]]:
    """`session_factory` es inyectable — mismo motivo que
    `app.retention.cli.main`: los tests de integración y el endpoint HTTP
    `POST /system-cleanup` necesitan apuntar a una base de datos distinta
    de la resuelta por `get_settings().database_url`; en uso real por
    cron directo siempre es `None`.

    Devuelve `{"purged_clinics": [str(clinic_id), ...]}` además de
    imprimir por stdout (comportamiento sin cambios) — el mismo resultado
    que el endpoint HTTP puede reportar como JSON sin reimplementar este
    bucle."""
    session_factory = session_factory or get_session_factory()

    async with session_factory() as session:
        purged = await UnverifiedClinicCleanupService(session).purge()

    if not purged:
        print("[sin cambios] ninguna clínica supera el plazo sin verificar")
    for clinic in purged:
        print(f"[purgada] clínica {clinic.id} ({clinic.code}): {clinic.name}")

    return {"purged_clinics": [str(clinic.id) for clinic in purged]}


if __name__ == "__main__":
    asyncio.run(main())
