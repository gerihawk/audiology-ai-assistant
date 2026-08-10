"""MockAudioCostEstimator: siempre $0, sin relación con el coste real."""

from __future__ import annotations

from decimal import Decimal

from app.integrations.domain.audio_cost_estimator import CostEstimate, CostEstimateSource


class MockAudioCostEstimator:
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
        return CostEstimate(
            amount_usd=Decimal("0"),
            source=CostEstimateSource.MOCK,
            pricing_version=None,
            pricing_effective_date=None,
        )
