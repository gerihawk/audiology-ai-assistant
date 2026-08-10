"""Puerto CostEstimator. Ver docs/ai-pipeline-architecture.md §6.1."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class CostEstimator(Protocol):
    def estimate(
        self, *, provider: str, model: str | None, input_tokens: int, output_tokens: int
    ) -> Decimal: ...
