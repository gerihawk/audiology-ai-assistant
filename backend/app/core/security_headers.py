"""Cabeceras de seguridad HTTP (Fase 10.5)."""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        super().__init__(app)
        self._hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if self._hsts_enabled:
            # Solo en production: prometer HSTS sobre development
            # (http://localhost) sería falso — el navegador no debe forzar
            # HTTPS ahí.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
