"""Helpers para crear clínicas/usuarios ficticios directamente vía repositorio en los tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.current_user import CurrentUser
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository


def _now() -> datetime:
    return datetime.now(UTC)


async def create_clinic(
    session: AsyncSession, *, code: str | None = None, name: str = "Clínica de test"
) -> Clinic:
    clinic = Clinic(
        id=uuid.uuid4(),
        name=name,
        code=code or f"TEST-{uuid.uuid4().hex[:8]}",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    await SqlAlchemyClinicRepository().add(session, clinic)
    await session.commit()
    return clinic


async def create_user(
    session: AsyncSession,
    clinic_id: uuid.UUID,
    *,
    role: Role,
    email: str | None = None,
    display_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        clinic_id=clinic_id,
        email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.local",
        display_name=display_name or f"Usuario {role.value} de test",
        role=role,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )
    await SqlAlchemyUserRepository().add(session, user)
    await session.commit()
    return user


@dataclass(slots=True)
class ClinicWithUsers:
    clinic: Clinic
    admin: User
    audiologist: User
    viewer: User


async def create_clinic_with_users(session: AsyncSession) -> ClinicWithUsers:
    clinic = await create_clinic(session)
    admin = await create_user(session, clinic.id, role=Role.ADMIN)
    audiologist = await create_user(session, clinic.id, role=Role.AUDIOLOGIST)
    viewer = await create_user(session, clinic.id, role=Role.VIEWER)
    return ClinicWithUsers(clinic=clinic, admin=admin, audiologist=audiologist, viewer=viewer)


def dev_headers(user: User) -> dict[str, str]:
    return {"X-Dev-User-Id": str(user.id)}


def current_user_from(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        clinic_id=user.clinic_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
