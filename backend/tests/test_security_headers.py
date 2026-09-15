"""Test de las cabeceras de seguridad HTTP añadidas a toda respuesta —
Fase 10.5, ver app/core/security_headers.py."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware


def test_security_headers_present_on_any_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_hsts_absent_outside_production(client: TestClient) -> None:
    # La suite corre con ENVIRONMENT=test (ver conftest.py) — HSTS no debe
    # prometerse fuera de production (sobre http://localhost, por ejemplo).
    response = client.get("/health")

    assert "strict-transport-security" not in response.headers


def test_hsts_activo_en_staging() -> None:
    # Fase 10.7: `hsts_enabled=settings.is_production or settings.is_staging`
    # en app/main.py — reproducido aquí con una `Settings` real de staging,
    # mismo patrón que el resto de este fichero (app real vs. app mínima).
    settings = Settings(
        environment="staging",
        postgres_user="u",
        postgres_password="s3cret-enough",
        postgres_db="d",
        postgres_host="h",
        backend_cors_origins="https://app.example.com",
        auth_mode="real",
        jwt_secret_key="s3cret-enough-for-jwt-at-least-32-bytes",
        retention_cron_secret="s3cret-enough-for-retention",
    )
    assert settings.is_production or settings.is_staging

    app = FastAPI()
    app.add_middleware(
        SecurityHeadersMiddleware, hsts_enabled=settings.is_production or settings.is_staging
    )

    @app.get("/probe")
    def probe() -> dict[str, str]:
        return {"ok": "true"}

    client = TestClient(app)
    response = client.get("/probe")

    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"
