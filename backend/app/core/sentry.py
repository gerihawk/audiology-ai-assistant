"""Sentry — EXCLUSIVAMENTE error tracking (Fase 10.6).

Sin performance tracing (`traces_sample_rate=0`), sin Session Replay ni
Profiling (integraciones nunca añadidas). Saneamiento agresivo en
`_before_send`: cuerpo de request/response, variables locales de
traceback, cabeceras fuera de la lista blanca y parámetros de breadcrumbs
SQL — ver docs/privacy-and-security.md §2/§3/§6 y docs/data-model.md §2
para qué campos del dominio son PHI/PII real (identidad de `patients`,
contenido de transcripción/anamnesis en `ai_artifact_versions.content`,
notas administrativas de texto libre) frente a lo que no lo es (UUIDs,
roles, códigos de estado, nombres de endpoint).

`scope.user` se limita exclusivamente a `id` (UUID opaco) — ver
`tag_current_user` más abajo, enganchada en `get_current_user`
(core/deps.py) — nunca `email`/`display_name`/`ip_address`, aunque
`send_default_pii=False` ya evita que la SDK adjunte IP por su cuenta.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import sentry_sdk

from app.core.config import Settings

# Única lista blanca de cabeceras que sobrevive al saneamiento —
# ninguna de las dos puede contener PII/PHI y ambas ayudan a depurar
# (tipo de contenido, correlación con `RequestIdMiddleware`/logs JSON).
_HEADER_ALLOWLIST = {"content-type", "x-request-id"}


def _strip_request_and_response_bodies(event: dict[str, Any]) -> None:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value for key, value in headers.items() if key.lower() in _HEADER_ALLOWLIST
            }
    response = event.get("response")
    if isinstance(response, dict):
        response.pop("data", None)


def _strip_frame_locals(event: dict[str, Any]) -> None:
    # Defensa en profundidad: `include_local_variables=False` (init) ya
    # evita que la SDK adjunte `vars` en origen; esto cubre el caso de que
    # ese ajuste cambiara sin querer.
    exception = event.get("exception")
    if not isinstance(exception, dict):
        return
    for value in exception.get("values", []):
        frames = value.get("stacktrace", {}).get("frames", [])
        for frame in frames:
            frame.pop("vars", None)


def _strip_sql_breadcrumb_params(event: dict[str, Any]) -> None:
    breadcrumbs = event.get("breadcrumbs")
    items = breadcrumbs.get("values") if isinstance(breadcrumbs, dict) else breadcrumbs
    if not items:
        return
    for breadcrumb in items:
        if breadcrumb.get("category") != "query":
            continue
        data = breadcrumb.get("data")
        if isinstance(data, dict):
            # Conserva la sentencia parametrizada (placeholders); nunca los
            # valores reales de los parámetros — pueden ser contenido
            # clínico-adyacente (docs/privacy-and-security.md §2).
            data.pop("db.params", None)
            data.pop("db.params_list", None)


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    _strip_request_and_response_bodies(event)
    _strip_frame_locals(event)
    _strip_sql_breadcrumb_params(event)
    return event


def _before_send_transaction(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    # `traces_sample_rate=0` implica que Sentry nunca genera transacciones
    # en la práctica — este hook no debería invocarse nunca. Se define de
    # todos modos, con el mismo saneamiento, como defensa en profundidad si
    # esa configuración cambiara sin querer en el futuro.
    _strip_request_and_response_bodies(event)
    return event


def init_sentry(settings: Settings) -> None:
    """No-op en cualquier entorno si `SENTRY_DSN` no está configurada."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # `RAILWAY_GIT_COMMIT_SHA`: variable inyectada por Railway (no
        # nuestra, no forma parte de `Settings`), solo poblada en deploys
        # disparados desde GitHub — `None` en local/test, que Sentry trata
        # como "sin release", no como error. Si tras un deploy real el
        # campo `release` aparece vacío en Sentry, es señal de que en este
        # proyecto la variable no llega hasta aquí (p. ej. disponible en
        # build-time del Dockerfile pero no en runtime del contenedor) —
        # revisarlo entonces, no asumir que funciona por compilar.
        release=os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        send_default_pii=False,
        traces_sample_rate=0,
        include_local_variables=False,
        before_send=_before_send,
        before_send_transaction=_before_send_transaction,
    )


def tag_request_id(request_id: str) -> None:
    """Etiqueta con `request_id` cualquier evento Sentry capturado durante
    la petición en curso — mismo identificador que `RequestIdMiddleware`
    ya genera y que ya usan `audit_logs`/`ai_generation_runs`
    (docs/data-model.md §2); no se introduce un segundo mecanismo."""
    if sentry_sdk.is_initialized():
        sentry_sdk.set_tag("request_id", request_id)


def tag_current_user(user_id: uuid.UUID) -> None:
    """Etiqueta `scope.user` con únicamente el `id` (UUID opaco) del
    usuario autenticado de la petición en curso — nunca `email`,
    `username` ni `ip_address` (explícito en el dict aunque
    `send_default_pii=False` ya evite que la SDK adjunte IP por su
    cuenta), ver docs/privacy-and-security.md §2."""
    if sentry_sdk.is_initialized():
        sentry_sdk.set_user({"id": str(user_id)})
