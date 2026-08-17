"""Tests de la migración `a1c3f9d6b2e4` (baseline_artifact_id/
baseline_version_id en `ai_artifacts`) — Hito 6.5.3, encargo §18.

Corre la cadena COMPLETA de migraciones contra una base de datos aislada
y desechable, creada y destruida por este propio módulo — nunca toca
`audiology_ai_assistant_test` (la base compartida por el resto de la
suite, gestionada por `conftest.py` vía `Base.metadata.create_all`, no
vía Alembic)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import NullPool, create_engine, inspect, text

from alembic import command
from app.core.config import get_settings

_SCRATCH_DB_NAME = "audiology_ai_assistant_migration_test"
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _admin_url(settings) -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )


def _scratch_url(settings) -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{_SCRATCH_DB_NAME}"
    )


def _scratch_engine(url: str):
    # `NullPool`: cada conexión se cierra al hacer checkin (fin del bloque
    # `with`), incluso si el test falla a mitad — sin esto, una conexión
    # colgada del pool por defecto bloquearía el `DROP DATABASE` del
    # teardown con `ObjectInUse`.
    return create_engine(url, poolclass=NullPool)


@pytest.fixture
def scratch_database_url():
    """Crea una base de datos desechable en el MISMO servidor Postgres ya
    configurado, y redirige `alembic/env.py` hacia ella durante el test —
    `env.py` construye su URL desde `get_settings().database_url`
    (`POSTGRES_DB`), no desde `Config.set_main_option`, así que hay que
    parchear la variable de entorno + limpiar el caché de `get_settings`
    (`@lru_cache`), no solo pasar la URL a `alembic.config.Config`."""
    settings = get_settings()
    admin_engine = _scratch_engine(_admin_url(settings)).execution_options(
        isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{_SCRATCH_DB_NAME}"'))
    admin_engine.dispose()

    original_postgres_db = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = _SCRATCH_DB_NAME
    get_settings.cache_clear()
    try:
        yield _scratch_url(settings)
    finally:
        if original_postgres_db is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = original_postgres_db
        get_settings.cache_clear()

        admin_engine = _scratch_engine(_admin_url(settings)).execution_options(
            isolation_level="AUTOCOMMIT"
        )
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB_NAME}"'))
        admin_engine.dispose()


def _alembic_config(db_url: str) -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def test_full_migration_chain_upgrades_cleanly_from_scratch(scratch_database_url):
    command.upgrade(_alembic_config(scratch_database_url), "head")

    engine = _scratch_engine(scratch_database_url)
    columns = {c["name"]: c for c in inspect(engine).get_columns("ai_artifacts")}
    engine.dispose()

    assert "baseline_artifact_id" in columns
    assert "baseline_version_id" in columns
    assert columns["baseline_artifact_id"]["nullable"] is True
    assert columns["baseline_version_id"]["nullable"] is True


def test_baseline_columns_have_correct_foreign_keys(scratch_database_url):
    command.upgrade(_alembic_config(scratch_database_url), "head")

    engine = _scratch_engine(scratch_database_url)
    foreign_keys = inspect(engine).get_foreign_keys("ai_artifacts")
    engine.dispose()

    baseline_artifact_fk = next(
        fk for fk in foreign_keys if fk["constrained_columns"] == ["baseline_artifact_id"]
    )
    assert baseline_artifact_fk["referred_table"] == "ai_artifacts"
    assert baseline_artifact_fk["referred_columns"] == ["id"]

    baseline_version_fk = next(
        fk for fk in foreign_keys if fk["constrained_columns"] == ["baseline_version_id"]
    )
    assert baseline_version_fk["referred_table"] == "ai_artifact_versions"
    assert baseline_version_fk["referred_columns"] == ["id"]


def test_downgrade_removes_baseline_columns(scratch_database_url):
    config = _alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "-1")

    engine = _scratch_engine(scratch_database_url)
    columns = {c["name"] for c in inspect(engine).get_columns("ai_artifacts")}
    engine.dispose()

    assert "baseline_artifact_id" not in columns
    assert "baseline_version_id" not in columns


def test_downgrade_then_upgrade_leaves_no_orphaned_index_or_constraint(scratch_database_url):
    """Downgrade -> upgrade dos veces seguidas no debe fallar por
    restos de índices/constraints mal nombrados — confirma que
    `create_foreign_key`/`drop_constraint` usan nombres estables."""
    config = _alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "-1")
    command.upgrade(config, "head")
    command.downgrade(config, "-1")
    command.upgrade(config, "head")

    engine = _scratch_engine(scratch_database_url)
    columns = {c["name"] for c in inspect(engine).get_columns("ai_artifacts")}
    engine.dispose()
    assert {"baseline_artifact_id", "baseline_version_id"} <= columns


def test_preexisting_rows_keep_baseline_columns_null_after_upgrade(scratch_database_url):
    """Simula el escenario real: una fila de `ai_artifacts` ya existente
    ANTES de aplicar esta migración debe quedar con `baseline_*=NULL` tras
    el upgrade — nunca con un valor inventado (sin backfill, §1 del
    encargo de 6.5.3)."""
    config = _alembic_config(scratch_database_url)
    # Todas las migraciones anteriores a esta — simula "estado antes de 6.5.3".
    command.upgrade(config, "edc67aea3044")

    engine = _scratch_engine(scratch_database_url)
    clinic_id = uuid.uuid4()
    user_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    session_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinics (id, name, code, is_active) "
                "VALUES (:id, 'Clínica scratch', 'SCRATCH-01', true)"
            ),
            {"id": clinic_id},
        )
        conn.execute(
            text(
                "INSERT INTO users (id, clinic_id, email, display_name, role, is_active) "
                "VALUES (:id, :clinic_id, 'scratch@example.com', 'Scratch', 'admin', true)"
            ),
            {"id": user_id, "clinic_id": clinic_id},
        )
        conn.execute(
            text(
                "INSERT INTO patients (id, clinic_id, internal_code, created_by, updated_by) "
                "VALUES (:id, :clinic_id, 'SCRATCH-001', :user_id, :user_id)"
            ),
            {"id": patient_id, "clinic_id": clinic_id, "user_id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO clinical_sessions "
                "(id, clinic_id, patient_id, professional_id, session_type, status, "
                "created_by, updated_by) "
                "VALUES (:id, :clinic_id, :patient_id, :user_id, 'initial_assessment', "
                "'completed', :user_id, :user_id)"
            ),
            {
                "id": session_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "user_id": user_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO ai_artifacts (id, clinical_session_id, artifact_type, status) "
                "VALUES (:id, :session_id, 'anamnesis', 'review_pending')"
            ),
            {"id": artifact_id, "session_id": session_id},
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = _scratch_engine(scratch_database_url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT baseline_artifact_id, baseline_version_id "
                "FROM ai_artifacts WHERE id = :id"
            ),
            {"id": artifact_id},
        ).one()
    engine.dispose()

    assert row.baseline_artifact_id is None
    assert row.baseline_version_id is None
