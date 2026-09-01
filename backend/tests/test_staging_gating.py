""""staging" tratado igual que "production" para gating de herramientas de
desarrollo (Fase 10.7), salvo dos excepciones deliberadas y sin tocar:
`app/seed.py` (el seed de desarrollo sigue permitido en staging) y
`app/main.py::_docs_kwargs_for` (los docs interactivos siguen visibles
fuera de production, staging incluido — ver tests/test_config.py)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.api.router import register_dev_tools
from app.core.config import Settings
from app.seed import run_seed


def _settings(environment: str, **overrides) -> Settings:
    base = {
        "environment": environment,
        "postgres_user": "u",
        "postgres_password": "s3cret-enough",
        "postgres_db": "d",
        "postgres_host": "h",
        "backend_cors_origins": "https://app.example.com",
        "auth_mode": "real",
        "jwt_secret_key": "s3cret-enough-for-jwt-at-least-32-bytes",
        "retention_cron_secret": "s3cret-enough-for-retention",
    }
    base.update(overrides)
    return Settings(**base)


# --- (c) register_dev_tools: no-op en staging, igual que en production ---


def test_register_dev_tools_es_no_op_en_staging() -> None:
    router = APIRouter()

    register_dev_tools(router, settings=_settings("staging"))

    assert router.routes == []


def test_register_dev_tools_registra_rutas_fuera_de_production_y_staging() -> None:
    router = APIRouter()

    register_dev_tools(router, settings=_settings("development"))

    assert len(router.routes) > 0


# --- (d) run_seed(): sigue permitido en staging (no SystemExit) ----------


async def test_run_seed_no_lanza_system_exit_en_staging(
    test_engine: AsyncEngine, monkeypatch
) -> None:
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr("app.seed.get_settings", lambda: _settings("staging"))
    monkeypatch.setattr("app.seed.get_session_factory", lambda: session_factory)

    # No debe lanzar `SystemExit` — a diferencia de `ENVIRONMENT=production`
    # (guardado por app/seed.py, no tocado en esta fase).
    await run_seed()
