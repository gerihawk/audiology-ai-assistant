"""Tabla de precios de modelos LLM del benchmark de generación — ver
docs/generation-benchmark.md §Costes.

Independiente de `app/integrations/pricing.py` (esa tabla es de
transcripción de audio — nunca mezclada, mismo principio de separación
que AssemblyAI/Deepgram dentro de esa tabla).

`estimate_cost()` usa el coste autoritativo que el propio OpenRouter
reporte en `usage.cost` cuando esté disponible
(`CostEstimateSource.PROVIDER`); si no hay ni coste reportado ni entrada
en la tabla, devuelve `amount_usd=None` con `source=UNKNOWN` — nunca un
`0` que pudiera confundirse con "gratis" (encargo §16: "nunca mezclar
provider reported cost con pricing table estimate").

Precios verificados el 2026-08-11 contra `https://openrouter.ai/api/v1/models`
(JSON público, campo `pricing.prompt`/`pricing.completion`, USD por
token) y la página individual de cada modelo en openrouter.ai — nunca de
memoria. Estructural media naranja de `openai/gpt-5.2`: no se pudo
confirmar `structured_outputs` en `supported_parameters` en la
verificación (la página no expuso la lista completa) — revisar de nuevo
antes de usarlo con `response_json_schema` en `LlmCompletionRequest`."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

PRICING_VERSION = "2026-08-11.1"
PRICING_EFFECTIVE_DATE: str | None = "2026-08-11"


class CostEstimateSource(StrEnum):
    PROVIDER = "provider"  # usage.cost de la respuesta de OpenRouter
    PRICING_TABLE = "pricing_table"  # MODEL_PRICING de este módulo
    UNKNOWN = "unknown"  # ningún origen disponible — nunca se inventa 0


@dataclass(slots=True, frozen=True)
class ModelPricing:
    input_price_per_million_tokens_usd: Decimal
    output_price_per_million_tokens_usd: Decimal


#: Model id exacto de OpenRouter -> precio, verificado el 2026-08-11 (ver
#: docstring del módulo). Candidatos del informe de modelos de la Fase
#: 6.2 — ampliar aquí si se añaden más, nunca hardcodeado en el runner.
MODEL_PRICING: dict[str, ModelPricing] = {
    "anthropic/claude-sonnet-5": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("2.00"),
        output_price_per_million_tokens_usd=Decimal("10.00"),
    ),
    "anthropic/claude-opus-5": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("5.00"),
        output_price_per_million_tokens_usd=Decimal("25.00"),
    ),
    "openai/gpt-5.2": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("1.75"),
        output_price_per_million_tokens_usd=Decimal("14.00"),
    ),
    "google/gemini-3.6-flash": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("1.50"),
        output_price_per_million_tokens_usd=Decimal("7.50"),
    ),
}


@dataclass(slots=True, frozen=True)
class CostEstimate:
    amount_usd: Decimal | None
    source: CostEstimateSource
    pricing_version: str | None
    pricing_effective_date: str | None


def estimate_cost(
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    provider_reported_cost_usd: str | None,
) -> CostEstimate:
    if provider_reported_cost_usd is not None:
        return CostEstimate(
            amount_usd=Decimal(provider_reported_cost_usd),
            source=CostEstimateSource.PROVIDER,
            pricing_version=None,
            pricing_effective_date=None,
        )

    pricing = MODEL_PRICING.get(model)
    if pricing is None or input_tokens is None or output_tokens is None:
        return CostEstimate(
            amount_usd=None,
            source=CostEstimateSource.UNKNOWN,
            pricing_version=None,
            pricing_effective_date=None,
        )

    amount = (
        Decimal(input_tokens) * pricing.input_price_per_million_tokens_usd
        + Decimal(output_tokens) * pricing.output_price_per_million_tokens_usd
    ) / Decimal(1_000_000)
    return CostEstimate(
        amount_usd=amount,
        source=CostEstimateSource.PRICING_TABLE,
        pricing_version=PRICING_VERSION,
        pricing_effective_date=PRICING_EFFECTIVE_DATE,
    )
