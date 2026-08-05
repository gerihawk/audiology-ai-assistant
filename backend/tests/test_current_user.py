from app.core.config import Settings
from app.core.current_user import FakeCurrentUserProvider


def _production_settings(**overrides) -> Settings:
    base = {
        "environment": "production",
        "postgres_user": "u",
        "postgres_password": "s3cret-enough",
        "postgres_db": "d",
        "postgres_host": "h",
        "backend_cors_origins": "https://app.example.com",
    }
    base.update(overrides)
    return Settings(**base)


def test_fake_current_user_provider_rejects_production() -> None:
    try:
        FakeCurrentUserProvider(_production_settings())
    except RuntimeError as exc:
        assert "production" in str(exc)
    else:
        raise AssertionError("FakeCurrentUserProvider debería rechazar ENVIRONMENT=production")


def test_fake_current_user_provider_allows_development() -> None:
    settings = Settings(
        environment="development",
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        postgres_host="h",
        backend_cors_origins="http://localhost:5173",
    )
    # No debe lanzar.
    FakeCurrentUserProvider(settings)
