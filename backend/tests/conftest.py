import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "http://localhost:5173")
# Fase 9, hito 9.1: JWT_SECRET_KEY es obligatorio (sin default de Python,
# mismo criterio que POSTGRES_PASSWORD) — este valor solo cubre pytest
# ejecutado fuera de Docker; `docker compose run backend pytest` ya recibe
# el JWT_SECRET_KEY real de docker-compose.yml/.env si está definido.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
# Fase 10.4: RETENTION_CRON_SECRET es obligatorio (mismo criterio que
# JWT_SECRET_KEY de arriba) — autentica al cron externo de
# POST /api/v1/retention/system-purge, no cubierto por dev_headers().
os.environ.setdefault("RETENTION_CRON_SECRET", "test-retention-cron-secret-not-for-production")
# Fase 12, hito 12.4: ONBOARDING_CLEANUP_CRON_SECRET es obligatorio (mismo
# criterio que RETENTION_CRON_SECRET de arriba) — autentica al cron externo
# de POST /api/v1/onboarding/system-cleanup, no cubierto por dev_headers().
os.environ.setdefault(
    "ONBOARDING_CLEANUP_CRON_SECRET", "test-onboarding-cleanup-cron-secret-not-for-production"
)
# Fase 13, hito 13.2: BILLING_RECONCILE_CRON_SECRET es obligatorio (mismo
# criterio que los dos anteriores) — autentica al cron externo de
# POST /api/v1/billing/reconcile, no cubierto por dev_headers().
os.environ.setdefault(
    "BILLING_RECONCILE_CRON_SECRET", "test-billing-reconcile-cron-secret-not-for-production"
)
# Fase 12, hito 12.5: FIELD_ENCRYPTION_KEYS/FIELD_ENCRYPTION_ACTIVE_KEY_ID
# son obligatorios (mismo criterio que los secretos de arriba) — clave de
# 32 bytes generada solo para tests, nunca usada fuera de esta suite. Un
# único key_id activo es suficiente aquí: los tests de rotación
# (test_field_encryption.py) fijan sus propias claves en el entorno antes
# de invocar field_encryption_cli, no dependen de este valor por defecto.
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", "1:HEFvJucNIlytjAspyvBhWs58nGaFik96u9LFGlo6wMA=")
os.environ.setdefault("FIELD_ENCRYPTION_ACTIVE_KEY_ID", "1")

# Aislamiento de la suite frente a variables de entorno "ambiente" del
# contenedor (Fase 6.3, corrección del punto 11; ampliado 2026-09-21 con
# las variables de Stripe): `docker compose run` hereda el mismo bloque
# `environment:` que `docker compose up`, así que valores reales de
# `.env` del usuario (routing LLM, API keys, límites de coste, y ahora
# también la cuenta de Stripe en modo test que Gerard fue configurando)
# llegarían a `Settings()` en cualquier test que no los pase
# explícitamente, haciendo que ese test dependa silenciosamente de la
# máquina en la que se ejecuta. Caso real detectado el 2026-09-21: al
# rellenar `.env` con `PAYMENT_GATEWAY=stripe` y las claves/Price IDs de
# Stripe reales, `test_webhook_activates_clinic_subscription` empezó a
# ejecutar la verificación de firma real de Stripe en vez de
# `MockPaymentGateway` (la suite siempre asume `PAYMENT_GATEWAY=mock`), y
# `test_create_checkout_session_with_unconfigured_plan_is_conflict` dejó
# de ver "Clínica grande" como un plan sin configurar. Se limpian aquí,
# antes de cualquier import que pueda construir `Settings()` (p. ej.
# `app.main`) — nunca se toca el fichero `.env` real del usuario, solo el
# entorno del proceso de test.
for _leaking_var in (
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_PROVIDER_SUMMARY",
    "LLM_PROVIDER_PATIENT_SUMMARY",
    "LLM_PROVIDER_MISSING_INFORMATION",
    "LLM_MODEL_SUMMARY",
    "LLM_MODEL_PATIENT_SUMMARY",
    "LLM_MODEL_MISSING_INFORMATION",
    "LLM_COST_LIMIT_ENFORCED",
    "MAX_LLM_COST_PER_SESSION_USD",
    "AI_PROCESSING_CONSENT_ENFORCED",
    "PAYMENT_GATEWAY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID_BASICO",
    "STRIPE_PRICE_ID_PROFESIONAL",
    "STRIPE_PRICE_ID_CLINICA_GRANDE",
    "STRIPE_PRICE_ID_CADENA_EMPRESA",
    "STRIPE_METERED_PRICE_ID_BASICO",
    "STRIPE_METERED_PRICE_ID_PROFESIONAL",
    "STRIPE_METERED_PRICE_ID_CLINICA_GRANDE",
    "STRIPE_METER_EVENT_NAME_BASICO",
    "STRIPE_METER_EVENT_NAME_PROFESIONAL",
    "STRIPE_METER_EVENT_NAME_CLINICA_GRANDE",
):
    os.environ.pop(_leaking_var, None)
del _leaking_var

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
    """Recrea la base de datos de test desde cero (drop + create + esquema
    actual de los modelos ORM), una sola vez por sesión de pytest.
    Deliberadamente síncrono (sin asyncio) para no depender del loop de
    eventos de ningún test concreto.

    Ampliación 2026-09-21: antes esta fixture solo creaba la base de datos
    si no existía y construía su esquema con `Base.metadata.create_all()`,
    que ÚNICAMENTE crea tablas nuevas — nunca altera una tabla ya existente
    para añadir una columna nueva. Como `postgres_data` es un volumen
    Docker persistente (ver docker-compose.yml), la base de datos de test
    sobrevivía sin cambios entre ejecuciones, así que cualquier migración
    que añadiera una columna a una tabla ya creada en un run anterior
    (p. ej. `negotiated_included_sessions` en `clinics`) dejaba el ORM y
    el esquema real de test desincronizados, con errores
    `psycopg.errors.UndefinedColumn` en gran parte de la suite. Se
    soluciona recreando la base de datos de test por completo en cada
    sesión de pytest: es barato (solo esquema, sin datos reales que
    conservar entre runs — cada test ya trunca sus propias tablas en
    `test_engine`) y garantiza que el esquema de test siempre coincide con
    los modelos ORM actuales, sin depender de que alguien recuerde borrar
    el volumen a mano tras cada migración nueva."""
    settings = get_settings()

    admin_engine = create_engine(_sync_admin_url(settings), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        # `WITH (FORCE)` (Postgres >= 13) desconecta a la fuerza cualquier
        # conexión residual a la base de datos de test (p. ej. de un run
        # anterior que no cerró limpio) para que el DROP no falle con
        # "database is being accessed by other users".
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
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
            # `current_version_id` (ai_artifacts <-> ai_artifact_versions) y,
            # desde el Hito 6.5.3, `baseline_artifact_id` (autorreferencial)/
            # `baseline_version_id` (-> ai_artifact_versions): tres FKs más
            # que `sorted_tables` no puede ordenar linealmente. Mismo
            # criterio que ya se aplicaba a `current_version_id`.
            await conn.execute(
                ai_artifacts.update().values(
                    current_version_id=None,
                    baseline_artifact_id=None,
                    baseline_version_id=None,
                )
            )
        # Nulling esas columnas solo desbloquea el DELETE de `ai_artifacts`
        # en sí — `sorted_tables()` sigue sin poder ordenar el ciclo
        # (schema estático, no depende de los valores de fila) y ese "no
        # puedo ordenar" arrastra su posición relativa frente a CUALQUIER
        # otra tabla del módulo AI Pipeline (`clinical_sessions` incluida,
        # no solo `ai_pipeline_runs`/`ai_generation_runs` — desde el Hito
        # 6.5.3 el ciclo autorreferencial de `baseline_artifact_id` lo hizo
        # visible). Se rompe borrando explícitamente, en orden de
        # dependencia real verificado a mano, todo el subgrafo del AI
        # Pipeline antes del bucle genérico — el resto (patients, users,
        # clinics, audit_logs...) sí es un grafo acíclico y `sorted_tables()`
        # lo ordena bien.
        for dependency_ordered_table_name in (
            "clinical_flags",
            "ai_artifact_versions",
            "ai_generation_runs",
            "ai_artifacts",
            "ai_pipeline_runs",
            "audio_recordings",
            "consents",
        ):
            if dependency_ordered_table_name in Base.metadata.tables:
                await conn.execute(Base.metadata.tables[dependency_ordered_table_name].delete())
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
