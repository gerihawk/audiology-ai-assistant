"""MockCostEstimator: coste cero, coherente con que todo es ficticio y gratuito en el MVP."""

from __future__ import annotations

from decimal import Decimal


class MockCostEstimator:
    def estimate(
        self, *, provider: str, model: str | None, input_tokens: int, output_tokens: int
    ) -> Decimal:
        return Decimal("0")
