from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.config import get_settings
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`: el default de `fileConfig` (True)
    # deshabilita permanentemente cualquier logger de la aplicación ya
    # creado en el proceso (p. ej. "app.requests"/"app.errors"/
    # "app.ai_pipeline", creados al importar app.main) que no esté listado
    # explícitamente en alembic.ini — detectado porque
    # tests/test_migration_baseline_columns.py invoca Alembic en el mismo
    # proceso que el resto de la suite (Fase 10.6, revisión de logging):
    # tras ese test, ningún log de la app volvía a propagarse. Sin efecto
    # en `alembic upgrade head` desde CLI (proceso propio, sin loggers
    # previos de la app que proteger).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
