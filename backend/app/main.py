"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.health import router as health_router
from app.api.router import v1_router
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.config import Settings, get_settings
from app.core.context import RequestIdMiddleware
from app.core.deps import get_configured_transcription_provider, get_current_user_provider
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.core.request_size_limit import RequestSizeLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.sentry import init_sentry

settings = get_settings()
configure_logging(settings.log_level)
# Antes de servir tráfico; no-op si SENTRY_DSN no está configurada (Fase
# 10.6, ver app/core/sentry.py). No añade middleware propio — la
# correlación con request_id vive en RequestIdMiddleware/core/context.py —
# así que no altera el orden de middlewares de la Fase 10.5 de más abajo.
init_sentry(settings)

request_logger = logging.getLogger("app.requests")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Falla rápido en el arranque si CurrentUserProvider está mal
    # configurado (p. ej. FakeCurrentUserProvider con ENVIRONMENT=production).
    get_current_user_provider()
    # Ídem para TRANSCRIPTION_PROVIDER (p. ej. "assemblyai" sin
    # ASSEMBLYAI_API_KEY) — ver app/integrations/factory.py.
    get_configured_transcription_provider()
    yield


def _docs_kwargs_for(settings: Settings) -> dict[str, None]:
    """/docs, /redoc y /openapi.json expuestos solo fuera de production
    (Fase 10, decisión nueva — no forma parte de la deuda de la Fase 8.4)."""
    if not settings.is_production:
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(
    title="Audiology AI Assistant API",
    version="0.1.0",
    lifespan=lifespan,
    **_docs_kwargs_for(settings),
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # `Content-Disposition` no está en la lista CORS-safelisted de headers
    # de respuesta (a diferencia de Content-Type/Content-Length): sin esto,
    # `fetch()` desde un origen distinto (frontend Vite en :5173, backend
    # en :8000) recibe el header en la red pero `Response.headers.get(...)`
    # devuelve `null` en el navegador. Necesario para que el frontend pueda
    # leer el nombre de fichero real de `GET .../export` en vez de
    # reconstruirlo — ver `ai-artifacts/{id}/export` y
    # `clinical-record/export`.
    expose_headers=["Content-Disposition"],
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    RequestSizeLimitMiddleware, max_body_bytes=settings.max_request_body_mb * 1024 * 1024
)
app.add_middleware(SlowAPIMiddleware)
# Última en añadirse == más externa (Starlette invierte el orden de
# `add_middleware`): así las cabeceras de seguridad también llegan a las
# respuestas 429/413 generadas por los middlewares anteriores, no solo a
# las respuestas normales de los endpoints.
app.add_middleware(
    SecurityHeadersMiddleware, hsts_enabled=settings.is_production or settings.is_staging
)

register_exception_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def handle_rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Demasiadas solicitudes. Inténtalo de nuevo en unos instantes.",
            }
        },
    )


app.include_router(health_router)
app.include_router(v1_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Registra método, ruta, código de estado y duración. Nunca el cuerpo."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    request_logger.info(
        "request completada",
        extra={
            "context": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                # `getattr` con default: por seguridad ante cualquier
                # petición que no pase por `RequestIdMiddleware` (p. ej.
                # un test que monta una app mínima sin él) — en el flujo
                # real, `RequestIdMiddleware` ya lo fija antes de que este
                # middleware se ejecute (ver orden de `add_middleware`
                # más arriba).
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
    return response
