"""Comando de reconciliación diaria de suscripciones de Stripe — Fase 13,
hito 13.2 (docs/fase-13-rfc.md §6). Mismo patrón de bootstrap que
`app.onboarding.cleanup_cli`/`app.retention.cli`: sin scheduler en
proceso, pensado para que un cron externo (el cron dedicado de Railway en
el entorno de despliegue real, ver ops/billing-reconciliation-cron/) lo
dispare periódicamente.

Uso local (docker-compose, mismo volumen/BD que el backend):
    docker compose run --rm backend python -m app.billing.reconcile_cli

En el entorno de despliegue real, un cron externo no tiene acceso a ese
contenedor: dispara en su lugar `POST /api/v1/billing/reconcile` (ver
app/billing/api/router.py), que llama a `main()` desde dentro del propio
proceso del backend — mismo patrón que
`POST /api/v1/onboarding/system-cleanup`/
`POST /api/v1/retention/system-purge`.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.service import BillingService
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.db import get_session_factory


async def main(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, list[str]]:
    """`session_factory` es inyectable — mismo motivo que
    `app.onboarding.cleanup_cli.main`/`app.retention.cli.main`: los tests
    de integración y el endpoint HTTP `POST /reconcile` necesitan apuntar
    a una base de datos distinta de la resuelta por
    `get_settings().database_url`; en uso real por cron directo siempre es
    `None`."""
    session_factory = session_factory or get_session_factory()

    async with session_factory() as session:
        result = await BillingService(session).reconcile_subscriptions()

    if not result["reconciled_clinics"] and not result["overage_reported_clinics"]:
        print(
            f"[sin cambios] {len(result['checked_clinics'])} clínica(s) comprobada(s), "
            "ninguna deriva de estado ni overage que reportar"
        )
    for clinic_id in result["reconciled_clinics"]:
        print(f"[reconciliada] clínica {clinic_id}: subscription_status corregido")
    for clinic_id in result["overage_reported_clinics"]:
        print(f"[overage reportado] clínica {clinic_id}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
