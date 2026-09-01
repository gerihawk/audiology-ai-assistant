"""`request_id` en el logging estructurado (Fase 10.6, corrección de
revisión): `log_requests` (app/main.py) y `handle_unexpected_error`
(app/core/errors.py) deben incluir `request_id` en `record.context`, para
poder correlacionar logs de una misma petición — mismo identificador que
`RequestIdMiddleware` ya expone en la cabecera `X-Request-ID` de la
respuesta y que Sentry ya etiqueta (`app/core/sentry.py`, no tocado aquí).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import REQUEST_ID_HEADER, RequestIdMiddleware
from app.core.errors import register_exception_handlers
from app.main import log_requests


def test_log_requests_incluye_request_id_y_coincide_con_la_cabecera_de_respuesta(
    client: TestClient, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="app.requests")

    response = client.get("/health", headers={REQUEST_ID_HEADER: "req-log-test-1"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-log-test-1"
    record = next(r for r in caplog.records if r.name == "app.requests")
    assert record.context["request_id"] == "req-log-test-1"


async def test_log_requests_no_lanza_si_la_peticion_no_paso_por_request_id_middleware(
    caplog,
) -> None:
    # `getattr(request.state, "request_id", None)`: una petición que nunca
    # pasó por `RequestIdMiddleware` (como esta, construida a mano) no debe
    # romper el logging — se llama a la función real de app/main.py
    # directamente, sin duplicar su lógica.
    caplog.set_level(logging.INFO, logger="app.requests")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/no-request-id",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)

    async def call_next(_request: Request) -> Response:
        return Response(status_code=200)

    response = await log_requests(request, call_next)

    assert response.status_code == 200
    record = next(r for r in caplog.records if r.name == "app.requests")
    assert record.context["request_id"] is None


def test_handle_unexpected_error_incluye_request_id_en_el_log(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="app.errors")

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom", headers={REQUEST_ID_HEADER: "req-error-test-1"})

    assert response.status_code == 500
    record = next(r for r in caplog.records if r.name == "app.errors")
    assert record.context["request_id"] == "req-error-test-1"
