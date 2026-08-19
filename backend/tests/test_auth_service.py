"""Tests de AuthService.login — Fase 9, hito 9.1. Mismo mensaje de error
genérico para email inexistente y contraseña incorrecta (evita
enumeración de usuarios)."""

from __future__ import annotations

from unittest.mock import patch

import bcrypt
import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import _DUMMY_PASSWORD_HASH, AuthService
from app.core.config import get_settings
from app.core.current_user import JWT_ALGORITHM
from app.core.exceptions import UnauthenticatedError
from tests.factories import ClinicWithUsers, create_user

_PASSWORD = "correcta-y-ficticia"


async def test_login_with_correct_credentials_returns_valid_jwt(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
    )
    service = AuthService(db_session)

    token = await service.login(user.email, _PASSWORD)

    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[JWT_ALGORITHM])
    assert payload["sub"] == str(user.id)


async def test_login_with_nonexistent_email_and_wrong_password_share_the_same_message(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
    )
    service = AuthService(db_session)

    with pytest.raises(UnauthenticatedError) as wrong_password_exc:
        await service.login(user.email, "contraseña-incorrecta")
    with pytest.raises(UnauthenticatedError) as nonexistent_email_exc:
        await service.login("no-existe@test.local", _PASSWORD)

    assert str(wrong_password_exc.value) == str(nonexistent_email_exc.value)


async def test_login_with_inactive_user_raises_unauthenticated(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    user = await create_user(
        db_session,
        clinic_with_users.clinic.id,
        role=clinic_with_users.admin.role,
        password=_PASSWORD,
        is_active=False,
    )
    service = AuthService(db_session)

    with pytest.raises(UnauthenticatedError):
        await service.login(user.email, _PASSWORD)


async def test_login_with_no_password_assigned_raises_unauthenticated(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    # Sin `password=`: password_hash queda en None (usuario "sin
    # contraseña asignada todavía") — nunca debe autenticar con éxito.
    user = await create_user(
        db_session, clinic_with_users.clinic.id, role=clinic_with_users.admin.role
    )
    service = AuthService(db_session)

    with pytest.raises(UnauthenticatedError):
        await service.login(user.email, "cualquier-cosa")


async def test_login_runs_bcrypt_checkpw_even_for_nonexistent_email(
    db_session: AsyncSession,
) -> None:
    """Documenta el arreglo del canal lateral de tiempo: sin él, un email
    inexistente respondía en cortocircuito, sin pasar por `bcrypt.checkpw`
    (deliberadamente lento) — eso hacía el tiempo de respuesta distinto al
    de una contraseña incorrecta sobre un email real, permitiendo enumerar
    emails válidos por latencia aunque el mensaje de error fuera idéntico.
    Aquí se comprueba que `checkpw` se invoca igualmente, comparando
    contra `_DUMMY_PASSWORD_HASH` en vez de saltárselo."""
    service = AuthService(db_session)

    with (
        patch("app.auth.service.bcrypt.checkpw", wraps=bcrypt.checkpw) as mock_checkpw,
        pytest.raises(UnauthenticatedError),
    ):
        await service.login("no-existe@test.local", "cualquier-cosa")

    mock_checkpw.assert_called_once()
    called_password, called_hash = mock_checkpw.call_args.args
    assert called_password == b"cualquier-cosa"
    assert called_hash == _DUMMY_PASSWORD_HASH.encode("utf-8")
