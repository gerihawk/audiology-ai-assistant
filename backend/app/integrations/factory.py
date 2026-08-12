"""Resolución de `TranscriptionProvider` por configuración (Fase 5).

Único punto del código que decide "qué proveedor está activo" —
`TRANSCRIPTION_PROVIDER=mock|assemblyai|deepgram`. Ningún otro módulo debe
ramificar sobre el nombre del proveedor: todos consumen la interfaz
`TranscriptionProvider`, nunca una implementación concreta. Añadir un
proveedor nuevo (OpenAI, Speechmatics...) es añadir una entrada a los
registros de abajo, no tocar el resto del sistema — ver
docs/transcription-benchmark.md.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.integrations.domain.audio_cost_estimator import AudioCostEstimator
from app.integrations.domain.language_model_provider import LanguageModelProvider
from app.integrations.domain.transcription_provider import TranscriptionProvider
from app.integrations.keyterms import AUDIOLOGY_KEYTERMS_ES, KEYTERM_SET_VERSION
from app.integrations.mocks.mock_audio_cost_estimator import MockAudioCostEstimator
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider
from app.integrations.mocks.mock_transcription_provider import MockTranscriptionProvider
from app.integrations.providers.anthropic_language_model_provider import (
    AnthropicLanguageModelProvider,
)
from app.integrations.providers.assemblyai_transcription_provider import (
    AssemblyAITranscriptionProvider,
)
from app.integrations.providers.deepgram_transcription_provider import (
    DeepgramTranscriptionProvider,
)
from app.integrations.providers.google_language_model_provider import (
    GoogleLanguageModelProvider,
)
from app.integrations.providers.openai_language_model_provider import (
    OpenAILanguageModelProvider,
)
from app.integrations.providers.pricing_table_audio_cost_estimator import (
    PricingTableAudioCostEstimator,
)


def _build_assemblyai_baseline(settings: Settings) -> TranscriptionProvider:
    """Perfil reproducible de la Fase 5 — sin ningún parámetro
    experimental. `TRANSCRIPTION_PROVIDER=assemblyai` (producción) y
    `--providers assemblyai_baseline` (benchmark) construyen exactamente
    lo mismo."""
    return AssemblyAITranscriptionProvider(
        api_key=settings.assemblyai_api_key,
        base_url=settings.assemblyai_base_url,
        language_code=settings.assemblyai_language_code,
        poll_interval_seconds=settings.assemblyai_poll_interval_seconds,
        poll_timeout_seconds=settings.assemblyai_poll_timeout_seconds,
    )


def _build_assemblyai_optimized(settings: Settings) -> TranscriptionProvider:
    """Perfil experimental (Fase 5.2, solo benchmark — nunca usado por
    `TRANSCRIPTION_PROVIDER`): añade `speech_models`/`speakers_expected`/
    Medical Mode/`keyterms_prompt` según `Settings`. Ver
    docs/transcription-benchmark.md §Experimento."""
    return AssemblyAITranscriptionProvider(
        api_key=settings.assemblyai_api_key,
        base_url=settings.assemblyai_base_url,
        language_code=settings.assemblyai_language_code,
        poll_interval_seconds=settings.assemblyai_poll_interval_seconds,
        poll_timeout_seconds=settings.assemblyai_poll_timeout_seconds,
        speech_models=[settings.assemblyai_optimized_speech_model],
        speakers_expected=settings.assemblyai_optimized_speakers_expected,
        medical_mode=settings.assemblyai_optimized_medical_mode,
        keyterms_prompt=(
            AUDIOLOGY_KEYTERMS_ES if settings.assemblyai_optimized_keyterms_enabled else None
        ),
        keyterm_set_version=(
            KEYTERM_SET_VERSION if settings.assemblyai_optimized_keyterms_enabled else None
        ),
    )


def _build_deepgram_nova3_baseline(settings: Settings) -> TranscriptionProvider:
    """Perfil reproducible (Fase 5.3): español, diarización, timestamps,
    utterances, smart_format, Nova-3 — sin keyterms. `"deepgram"`
    (producción) y `"deepgram_nova3_baseline"` (benchmark) construyen
    exactamente lo mismo, mismo criterio que `assemblyai`/
    `assemblyai_baseline`."""
    return DeepgramTranscriptionProvider(
        api_key=settings.deepgram_api_key,
        base_url=settings.deepgram_base_url,
        language_code=settings.deepgram_language_code,
        model=settings.deepgram_model,
        timeout_seconds=settings.deepgram_timeout_seconds,
    )


def _build_deepgram_nova3_keyterms(settings: Settings) -> TranscriptionProvider:
    """Perfil preparado pero NO llamado en la Fase 5.3 (ver
    docs/transcription-benchmark.md §Configuración inicial de Deepgram) —
    añade `keyterm` sobre el mismo perfil baseline."""
    return DeepgramTranscriptionProvider(
        api_key=settings.deepgram_api_key,
        base_url=settings.deepgram_base_url,
        language_code=settings.deepgram_language_code,
        model=settings.deepgram_model,
        timeout_seconds=settings.deepgram_timeout_seconds,
        keyterms=AUDIOLOGY_KEYTERMS_ES if settings.deepgram_keyterms_enabled else None,
        keyterm_set_version=KEYTERM_SET_VERSION if settings.deepgram_keyterms_enabled else None,
    )


#: Registro único de proveedores de transcripción — consumido tanto por la
#: app (un proveedor activo, vía `TRANSCRIPTION_PROVIDER`) como por
#: `benchmark/` (varios proveedores/perfiles a la vez, para comparar).
#: Añadir un proveedor nuevo (OpenAI, Speechmatics...) es añadir una
#: entrada aquí — ninguna otra parte del sistema cambia. Ver
#: docs/transcription-benchmark.md.
#:
#: `"assemblyai_baseline"`/`"assemblyai_optimized"` y
#: `"deepgram_nova3_baseline"`/`"deepgram_nova3_keyterms"` son perfiles de
#: `benchmark/` (Fase 5.2/5.3), nunca valores válidos de
#: `TRANSCRIPTION_PROVIDER` — la producción solo conoce
#: `"assemblyai"`/`"deepgram"` (idénticos a sus perfiles baseline).
TRANSCRIPTION_PROVIDER_FACTORIES: dict[str, Callable[[Settings], TranscriptionProvider]] = {
    "mock": lambda settings: MockTranscriptionProvider(),
    "assemblyai": _build_assemblyai_baseline,
    "assemblyai_baseline": _build_assemblyai_baseline,
    "assemblyai_optimized": _build_assemblyai_optimized,
    "deepgram": _build_deepgram_nova3_baseline,
    "deepgram_nova3_baseline": _build_deepgram_nova3_baseline,
    "deepgram_nova3_keyterms": _build_deepgram_nova3_keyterms,
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
    "assemblyai_baseline": lambda settings: PricingTableAudioCostEstimator(settings),
    "assemblyai_optimized": lambda settings: PricingTableAudioCostEstimator(settings),
    "deepgram": lambda settings: PricingTableAudioCostEstimator(settings),
    "deepgram_nova3_baseline": lambda settings: PricingTableAudioCostEstimator(settings),
    "deepgram_nova3_keyterms": lambda settings: PricingTableAudioCostEstimator(settings),
}


def build_audio_cost_estimator(
    settings: Settings, provider_name: str | None = None
) -> AudioCostEstimator:
    name = provider_name or settings.transcription_provider
    factory = AUDIO_COST_ESTIMATOR_FACTORIES.get(name)
    if factory is None:
        return MockAudioCostEstimator()
    return factory(settings)


#: Registro único de proveedores LLM directos (Fase 6.3) — infraestructura
#: reutilizable, NO se construye una instancia nueva por ejecución del
#: pipeline (ver docs/fase-6-rfc.md §10 hito 6.3, encargo Fase 6.3 punto
#: 4). Los tres proveedores reales quedan registrados desde el hito 6.3.5
#: — sus clases están verificadas contra documentación oficial (ver cada
#: módulo de `providers/`), pero ninguna llamada real se ha hecho todavía
#: (cero tráfico salvo autorización explícita posterior).
#:
#: Esta es la pieza de infraestructura de bajo nivel: qué SDK/vendor
#: genera el texto. El routing "qué artifact_type usa qué proveedor" vive
#: exclusivamente en `Settings.llm_provider_summary`/
#: `llm_provider_patient_summary`/`llm_provider_missing_information`
#: (routing estático, estos tres campos deciden qué entrada de este
#: registro se resuelve para cada artifact_type — nunca una constante
#: Python ni un router dinámico, ver docs/fase-6-rfc.md §6.1/§11.1
#: decisión 12).
LANGUAGE_MODEL_PROVIDER_FACTORIES: dict[str, Callable[[Settings], LanguageModelProvider]] = {
    "mock": lambda settings: MockLanguageModelProvider(),
    "anthropic": lambda settings: AnthropicLanguageModelProvider(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        timeout_seconds=settings.anthropic_timeout_seconds,
    ),
    "openai": lambda settings: OpenAILanguageModelProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    ),
    "google": lambda settings: GoogleLanguageModelProvider(
        api_key=settings.google_api_key,
        base_url=settings.google_base_url,
        timeout_seconds=settings.google_timeout_seconds,
    ),
}


def build_language_model_provider(settings: Settings, provider_name: str) -> LanguageModelProvider:
    """`provider_name` se pasa siempre explícitamente (a diferencia de
    `build_transcription_provider`): no existe un único
    `Settings.language_model_provider` global — cada artifact_type resuelve
    su propio `provider_name` desde su campo de routing correspondiente
    antes de llamar aquí."""
    try:
        factory = LANGUAGE_MODEL_PROVIDER_FACTORIES[provider_name]
    except KeyError as exc:
        raise ValueError(
            f"'{provider_name}' no es un proveedor de modelo de lenguaje reconocido. "
            f"Valores válidos: {', '.join(sorted(LANGUAGE_MODEL_PROVIDER_FACTORIES))}."
        ) from exc
    return factory(settings)
