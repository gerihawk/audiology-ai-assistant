"""Repositorio de User.

Usado por FakeCurrentUserProvider (resolución del usuario ficticio), por
el seed y, desde la Fase 12 (hito 12.1), por `OnboardingService` — sigue
sin `api/` propio (`users` no expone rutas de gestión directa; el alta de
un usuario nuevo pasa por `POST /clinics/signup` o, en la Fase 12.2, por
la aceptación de una invitación).
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.domain.entities import Role, User
from app.users.infrastructure.orm import UserORM


def _to_domain(row: UserORM) -> User:
    return User(
        id=row.id,
        clinic_id=row.clinic_id,
        email=row.email,
        display_name=row.display_name,
        role=Role(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        password_hash=row.password_hash,
        token_version=row.token_version,
    )


class SqlAlchemyUserRepository:
    async def get_active_by_id(self, session: AsyncSession, user_id: uuid.UUID) -> User | None:
        result = await session.execute(
            select(UserORM).where(UserORM.id == user_id, UserORM.is_active.is_(True))
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, session: AsyncSession, user_id: uuid.UUID) -> User | None:
        """Sin filtrar por `is_active`: permite distinguir "no existe" de
        "existe pero inactivo" en los llamadores que necesiten esa
        distinción (p. ej. asignar un profesional responsable)."""
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_all(self, session: AsyncSession) -> list[User]:
        result = await session.execute(select(UserORM).order_by(UserORM.created_at))
        return [_to_domain(row) for row in result.scalars().all()]

    async def list_eligible_professionals(
        self, session: AsyncSession, clinic_id: uuid.UUID
    ) -> list[User]:
        """Usuarios de `clinic_id` que pueden ser `professional_id` de una
        sesión clínica — misma regla que
        `ClinicalSessionService._validate_professional`: activo, rol
        `admin` o `audiologist` (nunca `viewer`). Alfabético por
        `display_name`: pensado para poblar un desplegable, a diferencia
        de `list_all` (orden de creación, sin filtrar)."""
        result = await session.execute(
            select(UserORM)
            .where(
                UserORM.clinic_id == clinic_id,
                UserORM.is_active.is_(True),
                UserORM.role.in_([Role.ADMIN.value, Role.AUDIOLOGIST.value]),
            )
            .order_by(UserORM.display_name)
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def add(self, session: AsyncSession, user: User) -> None:
        session.add(
            UserORM(
                id=user.id,
                clinic_id=user.clinic_id,
                email=user.email,
                display_name=user.display_name,
                role=user.role.value,
                is_active=user.is_active,
                password_hash=user.password_hash,
            )
        )

    async def set_password_hash(
        self, session: AsyncSession, user_id: uuid.UUID, password_hash: str
    ) -> None:
        """Usado por `app.seed` para asignar/backfillear la contraseña
        ficticia de desarrollo (Fase 9, hito 9.1) a usuarios ya
        existentes de una ejecución anterior del seed, sin duplicar la
        lógica de creación de `add()`."""
        await session.execute(
            update(UserORM).where(UserORM.id == user_id).values(password_hash=password_hash)
        )

    async def increment_token_version(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        """Revoca todos los JWT emitidos hasta ahora para este usuario
        (hallazgo D1) — incremento atómico en SQL, nunca leer-sumar-escribir
        en Python. No comete: lo hace el servicio llamador."""
        await session.execute(
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(token_version=UserORM.token_version + 1)
        )

    async def set_active(
        self, session: AsyncSession, user_id: uuid.UUID, *, is_active: bool
    ) -> None:
        """Usado por `OnboardingService.verify_email` (Fase 12, hito 12.1)
        para activar el admin creado por `POST /clinics/signup`, inactivo
        hasta ese momento."""
        await session.execute(
            update(UserORM).where(UserORM.id == user_id).values(is_active=is_active)
        )

    async def list_by_clinic(self, session: AsyncSession, clinic_id: uuid.UUID) -> list[User]:
        """Todos los usuarios de una clínica, activos o no — a diferencia
        de `list_eligible_professionals`, sin filtrar por rol ni actividad.
        Usado por `UnverifiedClinicCleanupService` (Fase 12, hito 12.4)
        para resolver qué `user_id` borrar (y, con ellos, sus
        `account_tokens`) antes de poder borrar la propia clínica."""
        result = await session.execute(select(UserORM).where(UserORM.clinic_id == clinic_id))
        return [_to_domain(row) for row in result.scalars().all()]

    async def delete_by_clinic(self, session: AsyncSession, clinic_id: uuid.UUID) -> None:
        """Borrado físico de todos los usuarios de una clínica — mismo
        llamador y mismo criterio que `ClinicRepository.delete` (ver su
        docstring): el que borra es responsable del orden (tokens antes
        que usuarios, usuarios antes que la clínica)."""
        await session.execute(delete(UserORM).where(UserORM.clinic_id == clinic_id))
