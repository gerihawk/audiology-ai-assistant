from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_db_session
from app.main import app


class _FakeSuccessSession:
    async def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeFailingSession:
    async def execute(self, *args: Any, **kwargs: Any) -> None:
        raise SQLAlchemyError("conexión simulada fallida")


async def _override_success() -> AsyncIterator[_FakeSuccessSession]:
    yield _FakeSuccessSession()


async def _override_failure() -> AsyncIterator[_FakeFailingSession]:
    yield _FakeFailingSession()


def test_ready_returns_ok_when_db_reachable(client: TestClient) -> None:
    app.dependency_overrides[get_db_session] = _override_success
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_ready_returns_503_when_db_unreachable(client: TestClient) -> None:
    app.dependency_overrides[get_db_session] = _override_failure
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unreachable"}
