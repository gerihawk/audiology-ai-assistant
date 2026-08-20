"""Comando de purga de retención: invocación única por ejecución, pensada
para que un cron externo (host o sidecar de docker-compose) la programe —
no hay scheduler en proceso. Mismo patrón de bootstrap que `app.seed`.

A diferencia de `app.seed`, SÍ puede ejecutarse con ENVIRONMENT=production:
es el entorno donde debe correr.

No hay `CurrentUser` que resolver de una petición HTTP: se recorren todos
los usuarios, se agrupan por clínica y se purga cada clínica actuando como
su primer admin activo (orden determinista por `created_at`). Una clínica
sin ningún admin activo se omite y se registra en stdout, sin abortar la
purga de las demás.

Uso local (docker-compose, mismo volumen de almacenamiento que el backend):
    docker compose run --rm backend python -m app.retention.cli

En el entorno de despliegue real (Fase 10.4), un cron externo no tiene
acceso a ese volumen — dispara en su lugar `POST /api/v1/retention/
system-purge` (ver app/retention/api/router.py), que llama a `main()` desde
dentro del propio proceso del backend.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.current_user import CurrentUser
from app.core.db import get_session_factory
from app.retention.service import RetentionCleanupService
from app.users.domain.entities import User
from app.users.infrastructure.repository import SqlAlchemyUserRepository


def _resolve_admin_per_clinic(users: list[User]) -> dict[uuid.UUID, User]:
    """Primer admin activo de cada clínica, en orden determinista.

    Asume `users` ya ordenados por `created_at` (como devuelve
    `UserRepository.list_all()`); el primer admin activo encontrado por
    clínica gana.
    """
    admin_per_clinic: dict[uuid.UUID, User] = {}
    for user in users:
        if user.role.value != "admin" or not user.is_active:
            continue
        admin_per_clinic.setdefault(user.clinic_id, user)
    return admin_per_clinic


async def main(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, dict[str, int] | list[str]]:
    """`session_factory` es inyectable para que los tests de integración (y,
    desde la Fase 10.4, el endpoint HTTP `POST /system-purge`) apunten a una
    base de datos distinta de la resuelta por `get_settings().database_url`;
    en uso real por cron directo siempre es `None`.

    Devuelve `{"purged": {str(clinic_id): <nº audios purgados>, ...},
    "omitted_clinics": [str(clinic_id), ...]}` además de imprimir por stdout
    (comportamiento sin cambios) — el mismo resultado que un caller HTTP
    puede reportar como JSON sin reimplementar este bucle."""
    session_factory = session_factory or get_session_factory()
    user_repository = SqlAlchemyUserRepository()

    async with session_factory() as session:
        all_users = await user_repository.list_all(session)

    clinic_ids = {user.clinic_id for user in all_users}
    admin_per_clinic = _resolve_admin_per_clinic(all_users)

    purged: dict[str, int] = {}
    omitted_clinics: list[str] = []

    for clinic_id in sorted(clinic_ids, key=str):
        admin = admin_per_clinic.get(clinic_id)
        if admin is None:
            print(f"[omitida]  clínica {clinic_id}: sin admin activo")
            omitted_clinics.append(str(clinic_id))
            continue

        current_user = CurrentUser(
            id=admin.id,
            clinic_id=admin.clinic_id,
            email=admin.email,
            display_name=admin.display_name,
            role=admin.role,
        )
        request_id = str(uuid.uuid4())
        async with session_factory() as session:
            purged_items = await RetentionCleanupService(session).purge(current_user, request_id)
        print(f"[procesada] clínica {clinic_id}: {len(purged_items)} audio(s) purgado(s)")
        purged[str(clinic_id)] = len(purged_items)

    return {"purged": purged, "omitted_clinics": omitted_clinics}


if __name__ == "__main__":
    asyncio.run(main())
