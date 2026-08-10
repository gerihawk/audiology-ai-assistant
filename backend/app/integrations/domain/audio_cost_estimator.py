"""Puerto AudioCostEstimator — estimación de coste por duración de audio.

Deliberadamente **distinto** de `CostEstimator` (`cost_estimator.py`):
ese puerto está pensado para facturación por tokens de un
`LanguageModelProvider` (Summary/ClinicalFlags/MissingInformation/
Anamnesis); la transcripción de audio se factura casi siempre por
duración (segundos/minutos/horas de audio procesado), no por tokens de
salida — mezclar ambos modelos de coste en la misma interfaz habría
producido estimaciones sin sentido. Ver
docs/transcription-benchmark.md §Pricing.

`CostEstimateSource` distingue explícitamente de dónde sale la cifra: un
`Mock*` (siempre 0, sin relación con el coste real), una tabla de precios
mantenida a mano (aproximación, no facturación autoritativa) o el propio
proveedor (si su respuesta incluyera un coste real — no es el caso de
AssemblyAI a día de hoy).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class CostEstimateSource(StrEnum):
    MOCK = "mock"
    PRICING_TABLE = "pricing_table"
    PROVIDER = "provider"


@dataclass(slots=True, frozen=True)
class CostEstimate:
    amount_usd: Decimal
    source: CostEstimateSource
    pricing_version: str | None
    pricing_effective_date: str | None


class AudioCostEstimator(Protocol):
    def estimate(
        self,
        *,
        provider: str,
        model: str | None,
        audio_duration_seconds: float,
        # --- Componentes de coste activos (Fase 5.2) — opcionales, para
        # que un estimador que sepa desglosar precios por add-on (p. ej.
        # PricingTableAudioCostEstimator) pueda hacerlo; uno que no los
        # necesite (MockAudioCostEstimator) simplemente los ignora. ---
        diarization: bool = False,
        medical_mode: bool = False,
        keyterms_prompt: bool = False,
    ) -> CostEstimate: ...
