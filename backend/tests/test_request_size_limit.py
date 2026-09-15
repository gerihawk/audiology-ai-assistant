"""Test del middleware de límite de tamaño de request — Fase 10.5, ver
app/core/request_size_limit.py.

Aislado en una app Starlette mínima (no la app completa): probar el
límite real de `MAX_REQUEST_BODY_MB` (60 MB por defecto) contra la app
completa exigiría enviar cuerpos de decenas de MB en cada test."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.request_size_limit import RequestSizeLimitMiddleware

_MAX_BYTES = 10


async def _echo(request: Request) -> PlainTextResponse:
    body = await request.body()
    return PlainTextResponse(f"ok:{len(body)}")


def _build_client() -> TestClient:
    app = Starlette(routes=[Route("/echo", _echo, methods=["POST"])])
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=_MAX_BYTES)
    return TestClient(app)


def test_request_within_limit_passes_through() -> None:
    client = _build_client()

    response = client.post("/echo", content=b"1234567890")  # exactamente 10 bytes

    assert response.status_code == 200
    assert response.text == "ok:10"


def test_request_above_limit_returns_413() -> None:
    client = _build_client()

    response = client.post("/echo", content=b"1234567890" * 2)  # 20 bytes > 10

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_entity_too_large"
