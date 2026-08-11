"""Manejo global y estructurado de errores."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    SchemaValidationError,
    UnauthenticatedError,
)

logger = logging.getLogger("app.errors")


_UNSAFE_ERROR_KEYS = frozenset({"input", "ctx", "url"})


def _strip_input_values(errors: list[dict]) -> list[dict]:
    """Elimina el valor enviado por el cliente y detalles internos del error.

    - `input`: evita reflejar contenido potencialmente sensible del cuerpo
      de la petición.
    - `ctx`: puede contener la excepción Python original (no serializable
      a JSON) detrás de un `field_validator` que lanza `ValueError`; el
      mensaje legible ya está en `msg`.
    - `url`: enlace a la documentación de Pydantic, ruido innecesario.
    """
    return [{k: v for k, v in error.items() if k not in _UNSAFE_ERROR_KEYS} for error in errors]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Solicitud inválida.",
                    "details": _strip_input_values(exc.errors()),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    @app.exception_handler(NotFoundError)
    async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {"code": "not_found", "message": str(exc) or "Recurso no encontrado."}
            },
        )

    @app.exception_handler(ConflictError)
    async def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "conflict", "message": str(exc), "field": exc.field}},
        )

    @app.exception_handler(SchemaValidationError)
    async def handle_schema_validation_error(
        request: Request, exc: SchemaValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "schema_validation_error",
                    "message": str(exc),
                    "details": exc.errors,
                }
            },
        )

    @app.exception_handler(ForbiddenError)
    async def handle_forbidden(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": {"code": "forbidden", "message": str(exc) or "No autorizado."}},
        )

    @app.exception_handler(UnauthenticatedError)
    async def handle_unauthenticated(request: Request, exc: UnauthenticatedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {"code": "unauthenticated", "message": str(exc) or "No autenticado."}
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Error no controlado",
            extra={"context": {"method": request.method, "path": request.url.path}},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {"code": "internal_error", "message": "Ha ocurrido un error interno."}
            },
        )
