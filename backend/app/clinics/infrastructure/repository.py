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
        current_period_started_at=row.current_period_started_at,
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
                current_period_started_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .returning(ClinicORM)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_by_stripe_subscription_id(
        self, session: AsyncSession, stripe_subscription_id: str
    ) -> list[Clinic]:
        """Fase 13, hito 13.2 — resuelve a qué `Clinic`(s) aplicar un evento
        de ciclo de vida de la suscripción (`customer.subscription.*`,
        `invoice.*`). Devuelve una LISTA, no una sola `Clinic`: el nivel
        Cadena/Empresa comparte el mismo `stripe_subscription_id` entre
        varias filas (docs/fase-13-rfc.md §3.3) — el llamador debe aplicar
        el mismo cambio a todas."""
        result = await session.execute(
            select(ClinicORM).where(ClinicORM.stripe_subscription_id == stripe_subscription_id)
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def list_with_stripe_subscription(self, session: AsyncSession) -> list[Clinic]:
        """Fase 13, hito 13.2 — candidatas al cron de reconciliación diaria:
        toda `Clinic` que ya completó el alta de facturación (tiene
        `stripe_subscription_id`), sin filtrar por `subscription_status`:
        la reconciliación existe precisamente para detectar cuándo ese
        campo ya no refleja el estado real en Stripe."""
        result = await session.execute(
            select(ClinicORM).where(ClinicORM.stripe_subscription_id.is_not(None))
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def update_subscription_status(
        self, session: AsyncSession, clinic_id: uuid.UUID, *, subscription_status: str
    ) -> Clinic | None:
        """Fase 13, hito 13.2 — aplica `customer.subscription.updated`/
        `customer.subscription.deleted` (o una corrección de
        `reconcile_subscriptions`): sincroniza solo el estado, sin tocar
        `plan`/`sessions_used_this_period`/`current_period_started_at` (eso
        es exclusivo de `set_billing_fields`/`start_new_billing_period`)."""
        result = await session.execute(
            update(ClinicORM)
            .where(ClinicORM.id == clinic_id)
            .values(subscription_status=subscription_status, updated_at=datetime.now(UTC))
            .returning(ClinicORM)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def start_new_billing_period(
        self, session: AsyncSession, clinic_id: uuid.UUID, *, period_started_at: datetime
    ) -> Clinic | None:
        """Fase 13, hito 13.2 — aplica `invoice.paid`: cada factura pagada
        marca el inicio de un nuevo periodo de facturación, así que el
        contador de uso se reinicia (mismo criterio que `set_billing_fields`
        en el alta) y el estado vuelve a `active` (una factura solo se paga
        si la suscripción está al día)."""
        result = await session.execute(
            update(ClinicORM)
            .where(ClinicORM.id == clinic_id)
            .values(
                subscription_status="active",
                sessions_used_this_period=0,
                current_period_started_at=period_started_at,
                updated_at=datetime.now(UTC),
            )
            .returning(ClinicORM)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def increment_sessions_used(
        self, session: AsyncSession, clinic_id: uuid.UUID
    ) -> Clinic | None:
        """Fase 13, hito 13.2 — una unidad consumida del tope de
        sesiones/mes: incremento atómico en SQL (`sessions_used_this_period
        + 1`), nunca leer-modificar-escribir desde Python, para que dos
        disparos concurrentes del pipeline no se pisen entre sí."""
        result = await session.execute(
            update(ClinicORM)
            .where(ClinicORM.id == clinic_id)
            .values(
                sessions_used_this_period=ClinicORM.sessions_used_this_period + 1,
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
