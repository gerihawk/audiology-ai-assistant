"""Test de las cabeceras de seguridad HTTP añadidas a toda respuesta —
Fase 10.5, ver app/core/security_headers.py."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
