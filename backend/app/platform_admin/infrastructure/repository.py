"""Repositorio de PlatformOperator. Mismo patrón que
`SqlAlchemyUserRepository` (app/users/infrastructure/repository.py), pero
sobre su propia tabla — ver docstring de `PlatformOperatorORM`."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_admin.domain.entities import PlatformOperator
from app.platform_admin.infrastructure.orm import PlatformOperatorORM


def _to_domain(row: PlatformOperatorORM) -> PlatformOperator:
    return PlatformOperator(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        password_hash=row.password_hash,
        token_version=row.token_version,
    )


class SqlAlchemyPlatformOperatorRepository:
    async def get_by_email(self, session: AsyncSession, email: str) -> PlatformOperator | None:
        result = await session.execute(
            select(PlatformOperatorORM).where(PlatformOperatorORM.email == email)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_active_by_id(
        self, session: AsyncSession, operator_id: uuid.UUID
    ) -> PlatformOperator | None:
        result = await session.execute(
            select(PlatformOperatorORM).where(
                PlatformOperatorORM.id == operator_id,
                PlatformOperatorORM.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def add(self, session: AsyncSession, operator: PlatformOperator) -> None:
        session.add(
            PlatformOperatorORM(
                id=operator.id,
                email=operator.email,
                display_name=operator.display_name,
                password_hash=operator.password_hash,
                is_active=operator.is_active,
            )
        )

    async def set_password_hash(
        self, session: AsyncSession, operator_id: uuid.UUID, password_hash: str
    ) -> None:
        """Usado por `app.platform_admin.cli reset-password` — nunca
        `add()` sobre un operador ya existente, que intentaría insertar
        una fila duplicada con la misma PK."""
        await session.execute(
            update(PlatformOperatorORM)
            .where(PlatformOperatorORM.id == operator_id)
            .values(password_hash=password_hash)
        )

    async def increment_token_version(self, session: AsyncSession, operator_id: uuid.UUID) -> None:
        """Mismo criterio que `SqlAlchemyUserRepository.increment_token_version`."""
        await session.execute(
            update(PlatformOperatorORM)
            .where(PlatformOperatorORM.id == operator_id)
            .values(token_version=PlatformOperatorORM.token_version + 1)
        )
