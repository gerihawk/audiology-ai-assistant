"""PricingTableCostEstimator: `CostEstimator` real para los tres
proveedores LLM directos (Fase 6.3.8).

Fuente productiva propia bajo `app/integrations/` — **nunca** importa
`benchmark/generation/pricing.py` (esa tabla está indexada por id de
OpenRouter y es explícitamente exclusiva del benchmark, ver
docs/generation-benchmark.md). Mismo criterio de separación ya aplicado
entre `app/integrations/pricing.py` (audio) y el pricing del benchmark de
transcripción.

Precios reutilizados de los ya verificados en el hito 6.2 (mismo modelo,
mismo precio de lista — OpenRouter hace pass-through sin margen del precio
oficial del vendor) — verificados originalmente el 2026-08-11 contra
`https://openrouter.ai/api/v1/models`, re-declarados aquí por id **nativo**
del vendor (nunca el id namespaced de OpenRouter) para no depender de
`benchmark/`. Cualquier corrección de precio futura se hace en este único
punto, nunca disperso por el código.

**Contrato de `CostEstimator` sin ampliar** (encargo Fase 6.3.8: "si el
contrato actual no puede distinguir source sin romper el contrato, no lo
amplíes automáticamente"): `estimate()` sigue devolviendo únicamente un
`Decimal`, sin un campo adicional para "origen" del precio — no hacía
falta ampliarlo para cumplir el RFC, que solo exige que el coste nunca sea
0 artificial y que un modelo desconocido se trate de forma segura. Un
modelo sin precio conocido no devuelve `Decimal("0")` (se confundiría con
"gratis") ni un valor inventado: lanza `UnknownModelPricingError`
explícitamente, bloqueando el step por completo antes de poder invocar al
proveedor — nunca un número inventado con apariencia de coste real.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Cambia esta versión cuando se actualice cualquier precio, para que
#: quede trazable en auditoría — mismo patrón que
#: `benchmark/generation/pricing.py::PRICING_VERSION` y
#: `app/integrations/pricing.py::PRICING_VERSION` (tablas independientes).
PRICING_VERSION = "2026-08-12.1"
#: Fecha en la que este repositorio confirmó estos precios (no
#: necesariamente la fecha en que el vendor los cambió).
PRICING_EFFECTIVE_DATE = "2026-08-12"


class UnknownModelPricingError(Exception):
    """El modelo no está en `MODEL_PRICING` — nunca se sustituye por
    `Decimal("0")` ni por una estimación inventada. Bloquea el step antes
    de invocar al proveedor (se lanza desde el presupuesto "peor caso"
    previo a la llamada en `run_provider_step`)."""

    def __init__(self, provider: str, model: str | None) -> None:
        super().__init__(
            f"Sin precio conocido para provider='{provider}' model='{model}'. "
            "Añade su entrada a MODEL_PRICING antes de activar este modelo en producción."
        )
        self.provider = provider
        self.model = model


@dataclass(slots=True, frozen=True)
class ModelPricing:
    input_price_per_million_tokens_usd: Decimal
    output_price_per_million_tokens_usd: Decimal


#: Id nativo del vendor -> precio, ver docstring del módulo. Ampliar aquí
#: al añadir un modelo nuevo — nunca hardcodeado disperso en el código
#: (mismo criterio que `TRANSCRIPTION_PROVIDER_FACTORIES` en factory.py).
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-opus-5": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("5.00"),
        output_price_per_million_tokens_usd=Decimal("25.00"),
    ),
    "gpt-5.2": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("1.75"),
        output_price_per_million_tokens_usd=Decimal("14.00"),
    ),
    "gemini-3.6-flash": ModelPricing(
        input_price_per_million_tokens_usd=Decimal("1.50"),
        output_price_per_million_tokens_usd=Decimal("7.50"),
    ),
}


class PricingTableCostEstimator:
    def estimate(
        self, *, provider: str, model: str | None, input_tokens: int, output_tokens: int
    ) -> Decimal:
        pricing = MODEL_PRICING.get(model) if model else None
        if pricing is None:
            raise UnknownModelPricingError(provider, model)

        return (
            Decimal(input_tokens) * pricing.input_price_per_million_tokens_usd
            + Decimal(output_tokens) * pricing.output_price_per_million_tokens_usd
        ) / Decimal(1_000_000)
