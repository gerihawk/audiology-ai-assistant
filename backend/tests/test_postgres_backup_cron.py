"""Tests de las funciones puras de `ops/postgres-backup-cron/backup.py`
(Fase 11, hito 11.3): validación de entorno, normalización de la URL,
nombre del objeto y mapeo de credenciales. Sin Postgres ni bucket real —
mismo patrón que `test_retention_cli.py` (lógica pura extraída, testeable
sin infraestructura). El resto del flujo (`pg_dump | age | aws s3 cp`) es
orquestación de subprocesos y se verifica en el restore de prueba del
hito 11.4, no aquí.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "postgres_backup_cron",
    Path(__file__).parents[2] / "ops" / "postgres-backup-cron" / "backup.py",
)
assert _SPEC is not None and _SPEC.loader is not None
backup = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = backup  # @dataclass necesita el módulo en sys.modules
_SPEC.loader.exec_module(backup)


_FULL_ENV = {
    "DATABASE_URL": "postgresql://u:p@host:5432/db",
    "POSTGRES_BACKUP_AGE_PUBLIC_KEY": "age1examplepublickey",
    "POSTGRES_BACKUP_BUCKET_ENDPOINT": "https://acct.eu.r2.cloudflarestorage.com",
    "POSTGRES_BACKUP_BUCKET_NAME": "audiology-pg-backups",
    "POSTGRES_BACKUP_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "POSTGRES_BACKUP_SECRET_ACCESS_KEY": "secret-example",
}


def test_load_config_reads_full_env() -> None:
    config = backup.load_config(_FULL_ENV)

    assert config.bucket_name == "audiology-pg-backups"
    assert config.database_url == "postgresql://u:p@host:5432/db"
    assert config.bucket_region == "auto"  # default cuando no se define


@pytest.mark.parametrize("missing_var", sorted(_FULL_ENV))
def test_load_config_rejects_missing_var(missing_var: str) -> None:
    env = {k: v for k, v in _FULL_ENV.items() if k != missing_var}

    with pytest.raises(KeyError, match=missing_var):
        backup.load_config(env)


def test_load_config_rejects_empty_var() -> None:
    with pytest.raises(KeyError, match="POSTGRES_BACKUP_AGE_PUBLIC_KEY"):
        backup.load_config({**_FULL_ENV, "POSTGRES_BACKUP_AGE_PUBLIC_KEY": ""})


def test_normalize_database_url_strips_sqlalchemy_driver() -> None:
    assert backup.normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"
    assert backup.normalize_database_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_object_key_is_scoped_and_fixed_width() -> None:
    key = backup.object_key(datetime(2026, 9, 2, 9, 23, 0, tzinfo=UTC))

    assert key == "production/2026-09-02T09-23-00Z.dump.age"


def test_object_key_sorts_chronologically_as_text() -> None:
    earlier = backup.object_key(datetime(2026, 1, 1, tzinfo=UTC))
    later = backup.object_key(datetime(2026, 12, 31, tzinfo=UTC))

    assert earlier < later


def test_aws_env_maps_backup_credentials() -> None:
    config = backup.load_config({**_FULL_ENV, "POSTGRES_BACKUP_BUCKET_REGION": "eu-west-1"})

    assert backup.aws_env(config) == {
        "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "secret-example",
        "AWS_DEFAULT_REGION": "eu-west-1",
    }
