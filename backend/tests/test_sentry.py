"""Tests de Sentry (Fase 10.6) — ver app/core/sentry.py.

Ningún test de este fichero llama a la red real: cuando se necesita
`sentry_sdk.init()` con un DSN, se le pasa un `Transport` en memoria que
nunca abre una conexión."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import REQUEST_ID_HEADER, RequestIdMiddleware
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user, get_current_user_provider, get_db_session
from app.core.sentry import _before_send, init_sentry
from app.users.domain.entities import Role


class _NullTransport(Transport):
    """Nunca abre una conexión de red — descarta cualquier envelope/evento."""

    def capture_envelope(self, envelope: Any) -> None:  # pragma: no cover - trivial
        pass

    def flush(self, timeout: float, callback: Any = None) -> None:  # pragma: no cover
        pass


def _init_test_sentry(before_send) -> None:
    sentry_sdk.init(
        dsn="https://public@o0.ingest.sentry.io/0",
        transport=_NullTransport(),
        send_default_pii=False,
        traces_sample_rate=0,
        include_local_variables=False,
        before_send=before_send,
    )


def teardown_function() -> None:
    # Restaura el estado "sin Sentry" para no filtrar el cliente falso de
    # este fichero a otros tests de la suite (sentry_sdk usa estado global).
    sentry_sdk.init(dsn=None)


def test_init_sentry_is_noop_without_dsn() -> None:
    from app.core.config import get_settings

    settings = get_settings().model_copy(update={"sentry_dsn": None})

    with patch("app.core.sentry.sentry_sdk.init") as mock_init:
        init_sentry(settings)

    mock_init.assert_not_called()


def test_before_send_strips_phi_like_request_data_and_headers() -> None:
    # Campo PHI/PII real simulado: nombre de paciente (patients.display_name)
    # y un fragmento de transcripción (ai_artifact_versions.content /
    # clinical_flags.source_excerpt) — nunca deben sobrevivir en un evento
    # enviado a un servicio de terceros (docs/privacy-and-security.md §2/§6).
    event = {
        "request": {
            "method": "POST",
            "data": {
                "display_name": "Juana Pérez",
                "notes": "paciente refiere tinnitus unilateral",
            },
            "headers": {
                "authorization": "Bearer secreto",
                "cookie": "session=abc",
                "content-type": "application/json",
                "x-request-id": "req-123",
                "x-dev-user-id": "11111111-1111-1111-1111-111111111111",
            },
        },
        "response": {"data": {"transcript": "el paciente refiere otalgia derecha"}},
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"function": "f", "vars": {"display_name": "Juana Pérez"}},
                        ]
                    }
                }
            ]
        },
        "breadcrumbs": {
            "values": [
                {
                    "category": "query",
                    "data": {
                        "db.statement": "SELECT * FROM patients WHERE display_name = %s",
                        "db.params": ["Juana Pérez"],
                    },
                }
            ]
        },
    }

    result = _before_send(event, {})

    assert result is not None
    assert "data" not in result["request"]
    assert result["request"]["headers"] == {
        "content-type": "application/json",
        "x-request-id": "req-123",
    }
    assert "data" not in result["response"]
    assert "vars" not in result["exception"]["values"][0]["stacktrace"]["frames"][0]
    breadcrumb_data = result["breadcrumbs"]["values"][0]["data"]
    assert "db.params" not in breadcrumb_data
    assert breadcrumb_data["db.statement"] == "SELECT * FROM patients WHERE display_name = %s"


def test_request_id_tag_matches_request_id_of_the_request_that_raised() -> None:
    captured: list[dict[str, Any]] = []

    def capture_and_drop(event: dict[str, Any], hint: Any) -> None:
        captured.append(event)
        return None

    _init_test_sentry(capture_and_drop)

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    # Un 500 no handled sale por ServerErrorMiddleware, fuera de nuestra
    # pila de middlewares — RequestIdMiddleware nunca llega a escribir el
    # header de respuesta en ese caso. Se fija el request_id explícitamente
    # en la petición (mismo mecanismo que un cliente/proxy que reenvía
    # X-Request-ID) para tener un valor de referencia determinista.
    response = client.get("/boom", headers={REQUEST_ID_HEADER: "test-req-id-777"})

    assert response.status_code == 500
    assert len(captured) == 1
    assert captured[0]["tags"]["request_id"] == "test-req-id-777"


def test_scope_user_tagged_with_only_uuid_id_on_authenticated_request() -> None:
    captured: list[dict[str, Any]] = []

    def capture_and_drop(event: dict[str, Any], hint: Any) -> None:
        captured.append(event)
        return None

    _init_test_sentry(capture_and_drop)

    user_id = uuid.uuid4()
    fixed_user = CurrentUser(
        id=user_id,
        clinic_id=uuid.uuid4(),
        # Presentes en `CurrentUser` (docs/data-model.md §2 `users`) para
        # confirmar que `tag_current_user` los ignora deliberadamente — si
        # cualquiera de los dos apareciera en `event["user"]`, el test de
        # más abajo lo detectaría.
        email="profesional.ficticio@example.com",
        display_name="Profesional Ficticio",
        role=Role.ADMIN,
    )

    class _StubProvider:
        async def get_current_user(self, request: Request, session: AsyncSession) -> CurrentUser:
            return fixed_user

    app = FastAPI()
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user_provider] = lambda: _StubProvider()

    @app.get("/boom")
    def boom(current_user: CurrentUser = Depends(get_current_user)) -> None:
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert len(captured) == 1
    assert captured[0]["user"] == {"id": str(user_id)}


def test_init_sentry_passes_railway_git_commit_sha_as_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    settings = get_settings().model_copy(
        update={"sentry_dsn": "https://public@o0.ingest.sentry.io/0"}
    )

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    with patch("app.core.sentry.sentry_sdk.init") as mock_init:
        init_sentry(settings)
    assert mock_init.call_args.kwargs["release"] == "abc123"

    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    with patch("app.core.sentry.sentry_sdk.init") as mock_init:
        init_sentry(settings)
    assert mock_init.call_args.kwargs["release"] is None
