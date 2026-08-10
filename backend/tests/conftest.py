import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "http://localhost:5173")

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import orm_registry  # noqa: E402,F401  (registra los modelos ORM)
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.patients.domain.entities import Patient  # noqa: E402
from tests.factories import ClinicWithUsers, create_clinic_with_users, create_patient  # noqa: E402

TEST_DB_NAME = "audiology_ai_assistant_test"


def _sync_admin_url(settings) -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )


def _test_db_url(settings) -> str:
    # El driver psycopg (v3) sirve tanto para el motor síncrono (setup del
    # esquema) como para el asíncrono (create_async_engine), sin necesidad
    # de dos drivers distintos.
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{TEST_DB_NAME}"
    )


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database() -> None:
    """Crea la base de datos de test (si no existe) y su esquema, una sola
    vez por sesión de pytest. Deliberadamente síncrono (sin asyncio) para
    no depender del loop de eventos de ningún test concreto."""
    settings = get_settings()

    admin_engine = create_engine(_sync_admin_url(settings), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    schema_engine = create_engine(_test_db_url(settings))
    Base.metadata.create_all(schema_engine)
    schema_engine.dispose()


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Motor async por test, apuntando a la base de datos de test aislada.

    Trunca todas las tablas al principio de cada test: garantiza
    independencia sin importar el orden de ejecución.
    """
    settings = get_settings()
    engine = create_async_engine(_test_db_url(settings))
    async with engine.begin() as conn:
        # `ai_artifacts.current_version_id` referencia a `ai_artifact_versions`,
        # que a su vez referencia a `ai_artifacts` — un ciclo que
        # `sorted_tables` no puede ordenar linealmente (mismo motivo por el
        # que la migración crea esa FK con ALTER TABLE aparte, ver
        # docs/data-model.md §10). Se rompe el ciclo poniendo esa columna a
        # NULL antes del borrado genérico en orden topológico inverso.
        if "ai_artifacts" in Base.metadata.tables:
            ai_artifacts = Base.metadata.tables["ai_artifacts"]
            await conn.execute(ai_artifacts.update().values(current_version_id=None))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP async contra la app real, con /api/v1/* resolviendo
    contra la base de datos de test (nunca la de desarrollo)."""
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_db_session, None)


@pytest_asyncio.fixture
async def clinic_with_users(db_session: AsyncSession) -> ClinicWithUsers:
    """Una clínica con un usuario admin/audiologist/viewer, lista para
    usar como cabecera X-Dev-User-Id en los tests de la API de pacientes."""
    return await create_clinic_with_users(db_session)


@pytest_asyncio.fixture
async def patient(db_session: AsyncSession, clinic_with_users: ClinicWithUsers) -> Patient:
    """Un paciente ficticio no archivado en la clínica de `clinic_with_users`."""
    return await create_patient(db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id)


@pytest.fixture
def client() -> TestClient:
    """Cliente síncrono para los tests de /health y /ready de la Fase 1
    (usan dependency_overrides propios con una sesión simulada)."""
    return TestClient(app)
