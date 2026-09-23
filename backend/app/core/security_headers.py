"""Cabeceras de seguridad HTTP (Fase 10.5; Content-Security-Policy añadida
al cerrar el hallazgo medio del red team, docs/security/red-team-app-2026-09-22.md
§C2)."""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

#: Esta API es JSON puro — nada que cargar como documento/script/estilo.
#: `frame-ancestors 'none'` es redundante con X-Frame-Options: DENY para
#: navegadores modernos, pero CSP es el mecanismo vigente (X-Frame-Options
#: está deprecado a favor de frame-ancestors).
_CSP_NO_DOCS = "default-src 'none'; frame-ancestors 'none'"

#: Solo cuando /docs (Swagger UI) y /redoc están activos (fuera de
#: production, ver `_docs_kwargs_for` en app/main.py). Verificado en vivo
#: contra /docs y /redoc reales (consola del navegador, no solo supuesto):
#: Swagger UI carga JS/CSS desde cdn.jsdelivr.net + un <script> inline;
#: ReDoc además carga Google Fonts (Montserrat/Roboto), su logo desde
#: cdn.redoc.ly, y crea un Web Worker desde un blob: (búsqueda interna) —
#: los tres bloqueados en la primera pasada de esta política y confirmados
#: con violaciones reales de CSP antes de añadir las excepciones.
_CSP_WITH_DOCS = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline' blob:; "
    "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, hsts_enabled: bool, docs_enabled: bool) -> None:
        super().__init__(app)
        self._hsts_enabled = hsts_enabled
        self._csp = _CSP_WITH_DOCS if docs_enabled else _CSP_NO_DOCS

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = self._csp
        if self._hsts_enabled:
            # Solo en production: prometer HSTS sobre development
            # (http://localhost) sería falso — el navegador no debe forzar
            # HTTPS ahí.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
