"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import v1_router
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.config import get_settings
from app.core.context import RequestIdMiddleware
from app.core.deps import get_configured_transcription_provider, get_current_user_provider
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

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


app = FastAPI(title="Audiology AI Assistant API", version="0.1.0", lifespan=lifespan)

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

register_exception_handlers(app)
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
            }
        },
    )
    return response
