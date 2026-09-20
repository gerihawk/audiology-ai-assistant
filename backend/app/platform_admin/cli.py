"""CLI para crear/gestionar operadores de la plataforma (Fase 14).

Deliberadamente sin ningún endpoint HTTP de alta: a diferencia de
`users` (que se da de alta vía `POST /clinics/signup` o aceptando una
invitación), un `platform_operator` es una identidad de altísimo
privilegio (ve/gestiona todas las clínicas) — su alta es siempre una
acción manual desde este CLI, nunca alcanzable desde la API pública.
Mismo patrón de invocación única que `app.core.field_encryption_cli`/
`app.seed`.

Uso:
    docker compose exec backend python -m app.platform_admin.cli create-operator \\
        --email gerard@ejemplo.com --display-name "Gerard"
    (pide la contraseña de forma interactiva, con getpass — nunca como
    argumento de línea de comandos, para que no quede en el historial de
    la shell ni en `docker compose logs`.)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import uuid
from datetime import UTC, datetime

import bcrypt

from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.db import get_session_factory
from app.platform_admin.domain.entities import PlatformOperator
from app.platform_admin.infrastructure.repository import SqlAlchemyPlatformOperatorRepository


async def create_operator(email: str, display_name: str, password: str) -> None:
    session_factory = get_session_factory()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    repository = SqlAlchemyPlatformOperatorRepository()

    async with session_factory() as session:
        existing = await repository.get_by_email(session, email)
        if existing is not None:
            raise SystemExit(
                f"Ya existe un operador con el email {email!r} — usa 'reset-password' "
                "para cambiarle la contraseña."
            )
        # `created_at`/`updated_at` no viajan a `PlatformOperatorORM.add()`
        # (la tabla los fija con `server_default=now()`) — se rellenan aquí
        # solo para satisfacer el tipo de `PlatformOperator`, nunca se usan.
        now = datetime.now(UTC)
        operator = PlatformOperator(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            is_active=True,
            created_at=now,
            updated_at=now,
            password_hash=password_hash,
        )
        await repository.add(session, operator)
        await session.commit()
    print(f"Operador creado: {email}")


async def reset_password(email: str, password: str) -> None:
    session_factory = get_session_factory()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    repository = SqlAlchemyPlatformOperatorRepository()

    async with session_factory() as session:
        operator = await repository.get_by_email(session, email)
        if operator is None:
            raise SystemExit(f"No existe ningún operador con el email {email!r}.")
        await repository.set_password_hash(session, operator.id, password_hash)
        await session.commit()
    print(f"Contraseña actualizada: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-operator")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--display-name", required=True)

    reset_parser = subparsers.add_parser("reset-password")
    reset_parser.add_argument("--email", required=True)

    args = parser.parse_args()
    password = getpass.getpass("Contraseña: ")
    password_confirm = getpass.getpass("Confirma la contraseña: ")
    if password != password_confirm:
        raise SystemExit("Las contraseñas no coinciden.")

    if args.command == "create-operator":
        asyncio.run(create_operator(args.email, args.display_name, password))
    elif args.command == "reset-password":
        asyncio.run(reset_password(args.email, password))


if __name__ == "__main__":
    main()
