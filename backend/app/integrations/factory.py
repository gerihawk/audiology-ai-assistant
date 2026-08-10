"""Resolución de `TranscriptionProvider` por configuración (Fase 5).

Único punto del código que decide "qué proveedor está activo" —
`TRANSCRIPTION_PROVIDER=mock|assemblyai`. Ningún otro módulo debe
ramificar sobre el nombre del proveedor: todos consumen la interfaz
`TranscriptionProvider`, nunca una implementación concreta. Añadir un
proveedor nuevo (Deepgram, OpenAI, Speechmatics...) es añadir una entrada
a `_FACTORIES`, no tocar el resto del sistema — ver
docs/transcription-benchmark.md.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.integrations.domain.audio_cost_estimator import AudioCostEstimator
from app.integrations.domain.transcription_provider import TranscriptionProvider
from app.integrations.mocks.mock_audio_cost_estimator import MockAudioCostEstimator
from app.integrations.mocks.mock_transcription_provider import MockTranscriptionProvider
from app.integrations.providers.assemblyai_transcription_provider import (
    AssemblyAITranscriptionProvider,
)
from app.integrations.providers.pricing_table_audio_cost_estimator import (
    PricingTableAudioCostEstimator,
)

#: Registro único de proveedores de transcripción — consumido tanto por la
#: app (un proveedor activo, vía `TRANSCRIPTION_PROVIDER`) como por
#: `benchmark/` (varios proveedores a la vez, para comparar). Añadir un
#: proveedor nuevo (Deepgram, OpenAI, Speechmatics...) es añadir una
#: entrada aquí — ninguna otra parte del sistema cambia. Ver
#: docs/transcription-benchmark.md.
TRANSCRIPTION_PROVIDER_FACTORIES: dict[str, Callable[[Settings], TranscriptionProvider]] = {
    "mock": lambda settings: MockTranscriptionProvider(),
    "assemblyai": lambda settings: AssemblyAITranscriptionProvider(
        api_key=settings.assemblyai_api_key,
        base_url=settings.assemblyai_base_url,
        language_code=settings.assemblyai_language_code,
        poll_interval_seconds=settings.assemblyai_poll_interval_seconds,
        poll_timeout_seconds=settings.assemblyai_poll_timeout_seconds,
    ),
}


def build_transcription_provider(
    settings: Settings, provider_name: str | None = None
) -> TranscriptionProvider:
    """`provider_name` por defecto es `settings.transcription_provider` (uso
    normal de la app); `benchmark/` lo pasa explícitamente para construir
    varios proveedores distintos con la misma factoría."""
    name = provider_name or settings.transcription_provider
    try:
        factory = TRANSCRIPTION_PROVIDER_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(
            f"'{name}' no es un proveedor de transcripción reconocido. Valores válidos: "
            f"{', '.join(sorted(TRANSCRIPTION_PROVIDER_FACTORIES))}."
        ) from exc
    return factory(settings)


#: Registro de estimadores de coste por duración de audio — ver
#: app/integrations/domain/audio_cost_estimator.py (por qué es un puerto
#: distinto de `CostEstimator`, pensado para tokens de LLM). "mock" evita
#: mostrar un coste real donde no lo hay; "assemblyai" usa la tabla de
#: precios centralizada (`app/integrations/pricing.py`) porque AssemblyAI
#: no devuelve un coste en su respuesta.
AUDIO_COST_ESTIMATOR_FACTORIES: dict[str, Callable[[Settings], AudioCostEstimator]] = {
    "mock": lambda settings: MockAudioCostEstimator(),
    "assemblyai": lambda settings: PricingTableAudioCostEstimator(settings),
}


def build_audio_cost_estimator(
    settings: Settings, provider_name: str | None = None
) -> AudioCostEstimator:
    name = provider_name or settings.transcription_provider
    factory = AUDIO_COST_ESTIMATOR_FACTORIES.get(name)
    if factory is None:
        return MockAudioCostEstimator()
    return factory(settings)
