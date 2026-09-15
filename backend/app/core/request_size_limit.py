"""Límite de tamaño de request a nivel de aplicación (Fase 10.5).

Defensa en profundidad por encima de la validación de negocio ya existente
`audio_max_size_mb` (app/audio/): esto es un techo genérico para rechazar
cuerpos anormalmente grandes en CUALQUIER endpoint antes de procesarlos, no
una regla específica de audio.

Limitación conocida y aceptada para esta ronda: solo compara contra la
cabecera `Content-Length`. Un cliente que envíe `Transfer-Encoding: chunked`
sin `Content-Length` no queda cubierto por este middleware.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self._max_body_bytes
        ):
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "request_entity_too_large",
                        "message": "El cuerpo de la solicitud supera el tamaño máximo permitido.",
                    }
                },
            )
        return await call_next(request)
