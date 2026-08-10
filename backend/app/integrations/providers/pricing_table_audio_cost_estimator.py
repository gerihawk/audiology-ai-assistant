"""PricingTableAudioCostEstimator: estimación basada en la tabla de
precios centralizada (`app/integrations/pricing.py`) — usado cuando el
proveedor real no devuelve un coste en su respuesta (caso de AssemblyAI
hoy). Ver docs/transcription-benchmark.md §Pricing.

Desde la Fase 5.2, el coste se calcula **por componentes**: precio base
del modelo + add-ons activos (diarización/Medical Mode/keyterms) — nunca
un precio plano fijo, para reflejar correctamente que un perfil
`assemblyai_optimized` puede costar más que `assemblyai_baseline`."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings
from app.integrations.domain.audio_cost_estimator import CostEstimate, CostEstimateSource
from app.integrations.pricing import PRICING_EFFECTIVE_DATE, PRICING_VERSION, price_per_second_usd


class PricingTableAudioCostEstimator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def estimate(
        self,
        *,
        provider: str,
        model: str | None,
        audio_duration_seconds: float,
        diarization: bool = False,
        medical_mode: bool = False,
        keyterms_prompt: bool = False,
    ) -> CostEstimate:
        price_per_second = price_per_second_usd(
            provider,
            model,
            self._settings,
            diarization=diarization,
            medical_mode=medical_mode,
            keyterms_prompt=keyterms_prompt,
        )
        amount = (
            price_per_second * Decimal(str(audio_duration_seconds))
            if price_per_second is not None
            else Decimal("0")
        )
        return CostEstimate(
            amount_usd=amount,
            source=CostEstimateSource.PRICING_TABLE,
            pricing_version=PRICING_VERSION,
            pricing_effective_date=PRICING_EFFECTIVE_DATE,
        )
