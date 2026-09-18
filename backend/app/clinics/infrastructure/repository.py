"""Repositorio mínimo de Clinic: sin API propia en la Fase 2, usado por el
seed; desde la Fase 12 (hito 12.4) también por
`UnverifiedClinicCleanupService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.orm import ClinicORM
from app.users.infrastructure.orm import UserORM


def _to_domain(row: ClinicORM) -> Clinic:
    return Clinic(
        id=row.id,
        name=row.name,
        code=row.code,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        stripe_customer_id=row.stripe_customer_id,
        stripe_subscription_id=row.stripe_subscription_id,
        subscription_status=row.subscription_status,
        plan=row.plan,
        sessions_used_this_period=row.sessions_used_this_period,
    )


class SqlAlchemyClinicRepository:
    async def get_by_code(self, session: AsyncSession, code: str) -> Clinic | None:
        result = await session.execute(select(ClinicORM).where(ClinicORM.code == code))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, session: AsyncSession, clinic_id: uuid.UUID) -> Clinic | None:
        result = await session.execute(select(ClinicORM).where(ClinicORM.id == clinic_id))
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def add(self, session: AsyncSession, clinic: Clinic) -> None:
        session.add(
            ClinicORM(
                id=clinic.id,
                name=clinic.name,
                code=clinic.code,
                is_active=clinic.is_active,
            )
        )

    async def list_unverified_older_than(
        self, session: AsyncSession, cutoff: datetime
    ) -> list[Clinic]:
        """Fase 12, hito 12.4 — candidatas a `UnverifiedClinicCleanupService`:
        clínicas creadas antes de `cutoff` sin ningún usuario activo
        (nunca verificaron el email del admin creado por
        `POST /clinics/signup`, o el admin fue el único usuario y sigue
        inactivo). Único método de este repositorio que consulta
        `UserORM` directamente (join cross-módulo) en vez de delegar en
        `UserRepository` — evita traer todos los usuarios a Python solo
        para comprobar una existencia."""
        result = await session.execute(
            select(ClinicORM).where(
                ClinicORM.created_at < cutoff,
                ~exists().where(UserORM.clinic_id == ClinicORM.id, UserORM.is_active.is_(True)),
            )
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def set_billing_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        *,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        subscription_status: str,
        plan: str,
    ) -> Clinic | None:
        """Aplica el resultado de `checkout.session.completed` (Fase 13,
        hito 13.1) — único evento de alta gestionado en este hito, ver
        docs/fase-13-rfc.md §4.1/§7. `sessions_used_this_period` se
        reinicia a 0: es el primer periodo de facturación de la
        suscripción recién creada."""
        result = await session.execute(
            update(ClinicORM)
            .where(ClinicORM.id == clinic_id)
            .values(
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                subscription_status=subscription_status,
                plan=plan,
                sessions_used_this_period=0,
                updated_at=datetime.now(UTC),
            )
            .returning(ClinicORM)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def delete(self, session: AsyncSession, clinic_id: uuid.UUID) -> None:
        """Borrado físico — solo lo usa `UnverifiedClinicCleanupService`
        sobre una clínica ya confirmada como fantasma (ver
        `list_unverified_older_than`); el llamador es responsable de
        borrar antes cualquier fila que referencie `clinic_id` (`users`,
        y transitivamente `account_tokens`) o la sentencia falla por la
        FK, nunca en cascada silenciosa."""
        await session.execute(delete(ClinicORM).where(ClinicORM.id == clinic_id))
