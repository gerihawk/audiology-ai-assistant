"""`SessionCostBudget` — límite duro de coste por sesión clínica, ver
docs/fase-6-rfc.md §6.3 y el encargo de la Fase 6.1, punto 9.

Puro dominio, sin BD ni proveedor: `AIPipelineService` lo construye con el
coste ya acumulado (consultado una vez vía
`AIGenerationRunRepository.sum_estimated_cost_for_session`) y el límite de
`Settings`, y lo hace circular por `PipelineExecutionContext` para que
cada `run_provider_step` compruebe el presupuesto restante antes de
invocar al proveedor — "el step no se invoca y falla con
`cost_limit_exceeded`" (§6.3), nunca una llamada ya hecha que se descarta
después. Los reintentos cuentan contra el mismo presupuesto porque
comparten la misma instancia de `SessionCostBudget` a lo largo del step.

Siempre en `Decimal` — nunca `float` para lógica monetaria (ver encargo,
punto 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class SessionCostBudget:
    #: `None` = límite desactivado (development/test por defecto, ver
    #: `Settings.llm_cost_limit_enforced`) — `would_exceed` nunca bloquea.
    limit_usd: Decimal | None
    accumulated_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    def remaining_usd(self) -> Decimal | None:
        if self.limit_usd is None:
            return None
        return self.limit_usd - self.accumulated_usd

    def would_exceed(self, potential_usd: Decimal) -> bool:
        if self.limit_usd is None:
            return False
        return self.accumulated_usd + potential_usd > self.limit_usd

    def record(self, actual_usd: Decimal) -> None:
        self.accumulated_usd += actual_usd
