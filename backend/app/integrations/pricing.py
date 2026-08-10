"""Tabla de precios centralizada para estimación de coste de transcripción
por duración de audio — ver docs/transcription-benchmark.md §Pricing.

**Nunca facturación autoritativa.** Los valores de `_PRICE_PER_HOUR_USD`
son una aproximación orientativa (conocimiento general, no verificada
contra la página de precios vigente de cada proveedor en el momento de
uso) — antes de tomar cualquier decisión basada en coste real, confirma
el precio actual en la documentación oficial del proveedor y ajusta
`ASSEMBLYAI_PRICE_PER_HOUR_USD` (`.env`) si es necesario.

Todo precio nuevo se añade aquí, nunca hardcodeado en un `*CostEstimator`
concreto ni disperso por el código — un único punto de verdad, igual que
`TRANSCRIPTION_PROVIDER_FACTORIES` en `factory.py`.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings

#: Identifica esta versión de la tabla — cámbialo cuando actualices
#: cualquier precio, para que quede trazable en los resultados del
#: benchmark (`pricing_version` en `CostEstimate`).
PRICING_VERSION = "2026-08-11.1"
#: Fecha en la que se revisaron por última vez estos precios (no la fecha
#: en que el proveedor los cambió — la fecha en que ESTE repositorio los
#: verificó/actualizó).
PRICING_EFFECTIVE_DATE = "2026-08-11"

#: Precio por defecto (USD/hora) si `Settings` no especifica uno propio.
#: Orientativo — ver aviso arriba.
DEFAULT_ASSEMBLYAI_PRICE_PER_HOUR_USD = Decimal("0.15")


def assemblyai_price_per_hour_usd(settings: Settings) -> Decimal:
    return settings.assemblyai_price_per_hour_usd or DEFAULT_ASSEMBLYAI_PRICE_PER_HOUR_USD


def price_per_second_usd(provider: str, settings: Settings) -> Decimal | None:
    if provider == "assemblyai":
        return assemblyai_price_per_hour_usd(settings) / Decimal("3600")
    return None
