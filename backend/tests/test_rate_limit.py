"""Test de `_client_ip_key` — Fase 10.5, ver app/core/rate_limit.py.

Verificado en production (Railway): `get_remote_address` solo (sin esta
extracción de `X-Forwarded-For`) devuelve la IP del proxy de Railway, no
la del cliente real, y esa IP variaba entre peticiones — el rate limit de
login nunca se disparaba porque cada petición contaba como una "IP"
distinta."""

from __future__ import annotations

from starlette.requests import Request

from app.core.rate_limit import _client_ip_key


def _make_request(headers: dict[str, str], client: tuple[str, int] | None) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
        "method": "GET",
        "path": "/",
        "query_string": b"",
    }
    return Request(scope)


def test_client_ip_key_uses_first_value_of_x_forwarded_for() -> None:
    request = _make_request(
        {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}, client=("10.0.0.1", 12345)
    )

    assert _client_ip_key(request) == "203.0.113.7"


def test_client_ip_key_falls_back_to_remote_address_without_header() -> None:
    request = _make_request({}, client=("198.51.100.5", 4321))

    assert _client_ip_key(request) == "198.51.100.5"
