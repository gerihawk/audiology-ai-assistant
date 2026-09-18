"""Repositorio de idempotencia de webhooks de Stripe (Fase 13, hito 13.1)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.infrastructure.orm import StripeWebhookEventORM


class SqlAlchemyStripeWebhookEventRepository:
    async def has_processed(self, session: AsyncSession, event_id: str) -> bool:
        result = await session.execute(
            select(StripeWebhookEventORM.event_id).where(StripeWebhookEventORM.event_id == event_id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, session: AsyncSession, event_id: str, event_type: str) -> None:
        """`ON CONFLICT DO NOTHING` en vez de un `INSERT` liso: dos
        peticiones concurrentes del mismo evento reenviado por Stripe
        (ver docs/fase-13-rfc.md §5/§6) no deben poder violar la PK con una
        excepción no controlada — la comprobación de `has_processed` ya
        filtra el caso normal, esto es solo el cierre de la ventana de
        carrera entre ese `SELECT` y este `INSERT`."""
        await session.execute(
            pg_insert(StripeWebhookEventORM)
            .values(event_id=event_id, event_type=event_type)
            .on_conflict_do_nothing(index_elements=[StripeWebhookEventORM.event_id])
        )
