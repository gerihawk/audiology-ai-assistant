"""CLI idempotente para sembrar `prompt_templates` desde la fuente
canónica de producción (`app/ai_pipeline/prompts/`) — ver
docs/fase-6-rfc.md §7.4 y `app/ai_pipeline/prompts/catalog.py`.

Uso (dentro del contenedor backend, working dir /app):

    python -m app.ai_pipeline.seed_prompts

En desarrollo, adjudica `created_by` al usuario ficticio `admin@dev.local`
por defecto (mismo convenio que `app/seed.py`, ejecutar `make seed`
primero) — usa `--created-by <uuid>` en producción, donde ese usuario
ficticio no existe. Idempotente: una segunda ejecución no crea nada nuevo
si ya existe una plantilla activa por `(artifact_type, language)` — ver
`catalog.seed_prompt_templates`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import seed_prompt_templates
from app.core import orm_registry  # noqa: F401 — registra los modelos ORM
from app.core.db import get_session_factory
from app.users.infrastructure.repository import SqlAlchemyUserRepository

_DEFAULT_ADMIN_EMAIL = "admin@dev.local"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Siembra prompt_templates desde la fuente canónica app/ai_pipeline/prompts/."
    )
    parser.add_argument(
        "--created-by",
        help=(
            f"UUID del usuario autor. Por defecto busca '{_DEFAULT_ADMIN_EMAIL}' "
            "(solo development) — obligatorio en producción."
        ),
    )
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    session_factory = get_session_factory()

    async with session_factory() as session:
        if args.created_by:
            created_by = uuid.UUID(args.created_by)
        else:
            admin = await SqlAlchemyUserRepository().get_by_email(session, _DEFAULT_ADMIN_EMAIL)
            if admin is None:
                print(
                    f"No existe el usuario '{_DEFAULT_ADMIN_EMAIL}' y no se aportó "
                    "--created-by. En producción, pasa --created-by <uuid> explícitamente.",
                    file=sys.stderr,
                )
                return 1
            created_by = admin.id

        repository = SqlAlchemyPromptTemplateRepository()
        created = await seed_prompt_templates(session, repository, created_by=created_by)
        await session.commit()

    if created:
        for template in created:
            print(
                f"Creada: {template.name} v{template.version} "
                f"({template.artifact_type.value}/{template.language})"
            )
    else:
        print("Nada que sembrar — ya existe una plantilla activa por (artifact_type, language).")
    return 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
