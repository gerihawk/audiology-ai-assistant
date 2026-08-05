import pytest

from app.core.config import Settings


def _base_kwargs(**overrides: str) -> dict:
    kwargs = {
        "postgres_user": "user",
        "postgres_password": "s3cret",
        "postgres_db": "db",
        "postgres_host": "localhost",
        "backend_cors_origins": "https://app.example.com",
    }
    kwargs.update(overrides)
    return kwargs


def test_development_allows_wildcard_cors() -> None:
    settings = Settings(
        environment="development",
        backend_cors_origins="*",
        **{k: v for k, v in _base_kwargs().items() if k != "backend_cors_origins"},
    )
    assert settings.cors_origins == ["*"]


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="BACKEND_CORS_ORIGINS"):
        Settings(
            environment="production",
            **{
                **_base_kwargs(),
                "backend_cors_origins": "*",
            },
        )


def test_production_rejects_insecure_default_password() -> None:
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(
            environment="production",
            **{
                **_base_kwargs(),
                "postgres_password": "CHANGE_ME_LOCAL_ONLY",
            },
        )


def test_production_accepts_valid_configuration() -> None:
    settings = Settings(environment="production", **_base_kwargs())
    assert settings.is_production is True
    assert settings.cors_origins == ["https://app.example.com"]
