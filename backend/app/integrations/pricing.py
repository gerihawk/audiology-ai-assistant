"""Tabla de precios centralizada para estimación de coste de transcripción
por duración de audio — ver docs/transcription-benchmark.md §Pricing.

**Nunca facturación autoritativa.** Los valores de abajo se verificaron
contra las páginas oficiales de precios de cada proveedor
(https://www.assemblyai.com/pricing el 2026-08-11, Fase 5.2;
https://deepgram.com/pricing el 2026-08-11, Fase 5.3) — no están
inventados ni son una aproximación orientativa, pero los precios de
cualquier proveedor cambian con el tiempo: antes de tomar una decisión
basada en coste real, confirma el precio vigente en la documentación
oficial y ajusta la variable de entorno correspondiente si hace falta —
el estimador lee de `Settings`, nunca hay que tocar código para corregir
un precio.

Todo precio nuevo se añade aquí, nunca hardcodeado en un `*CostEstimator`
concreto ni disperso por el código — un único punto de verdad, igual que
`TRANSCRIPTION_PROVIDER_FACTORIES` en `factory.py`. **Los precios de cada
proveedor se calculan con funciones independientes, nunca mezclados** —
`assemblyai_*` y `deepgram_*` no comparten ninguna cifra ni fórmula.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings

#: Identifica esta versión de la tabla — cámbialo cuando actualices
#: cualquier precio, para que quede trazable en los resultados del
#: benchmark (`pricing_version` en `CostEstimate`).
PRICING_VERSION = "2026-08-11.2"
#: Fecha en la que se verificaron estos precios contra
#: https://www.assemblyai.com/pricing (no la fecha en que AssemblyAI los
#: cambió — la fecha en que este repositorio los confirmó).
PRICING_EFFECTIVE_DATE = "2026-08-11"

#: USD/hora por modelo base, verificados en la página oficial de precios.
ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD: dict[str, Decimal] = {
    "universal-3-5-pro": Decimal("0.21"),
    "universal-2": Decimal("0.15"),
}
#: Modelo asumido cuando no se especifica `speech_models` explícitamente
#: en la petición (comportamiento del perfil baseline) — Universal-2 ha
#: sido históricamente el modelo estándar de AssemblyAI; se usa como
#: supuesto conservador (el más barato) mientras la API no confirme con
#: certeza qué modelo resuelve por defecto.
ASSEMBLYAI_DEFAULT_BASE_MODEL = "universal-2"

#: USD/hora, add-ons — se suman aditivamente al precio base del modelo.
ASSEMBLYAI_DIARIZATION_ADDON_PER_HOUR_USD = Decimal("0.02")
ASSEMBLYAI_MEDICAL_MODE_ADDON_PER_HOUR_USD = Decimal("0.15")
ASSEMBLYAI_KEYTERMS_ADDON_PER_HOUR_USD = Decimal("0.05")

_ASSEMBLYAI_PROVIDER_NAMES = frozenset(
    {"assemblyai", "assemblyai_baseline", "assemblyai_optimized"}
)


def assemblyai_base_price_per_hour_usd(settings: Settings, model: str | None) -> Decimal:
    if settings.assemblyai_price_per_hour_usd is not None:
        return settings.assemblyai_price_per_hour_usd
    key = model if model in ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD else ASSEMBLYAI_DEFAULT_BASE_MODEL
    return ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD[key]


def assemblyai_diarization_addon_per_hour_usd(settings: Settings) -> Decimal:
    return (
        settings.assemblyai_diarization_addon_per_hour_usd
        if settings.assemblyai_diarization_addon_per_hour_usd is not None
        else ASSEMBLYAI_DIARIZATION_ADDON_PER_HOUR_USD
    )


def assemblyai_medical_mode_addon_per_hour_usd(settings: Settings) -> Decimal:
    return (
        settings.assemblyai_medical_mode_addon_per_hour_usd
        if settings.assemblyai_medical_mode_addon_per_hour_usd is not None
        else ASSEMBLYAI_MEDICAL_MODE_ADDON_PER_HOUR_USD
    )


def assemblyai_keyterms_addon_per_hour_usd(settings: Settings) -> Decimal:
    return (
        settings.assemblyai_keyterms_addon_per_hour_usd
        if settings.assemblyai_keyterms_addon_per_hour_usd is not None
        else ASSEMBLYAI_KEYTERMS_ADDON_PER_HOUR_USD
    )


def _assemblyai_price_per_second_usd(
    model: str | None,
    settings: Settings,
    *,
    diarization: bool,
    medical_mode: bool,
    keyterms_prompt: bool,
) -> Decimal:
    rate = assemblyai_base_price_per_hour_usd(settings, model)
    if diarization:
        rate += assemblyai_diarization_addon_per_hour_usd(settings)
    if medical_mode:
        rate += assemblyai_medical_mode_addon_per_hour_usd(settings)
    if keyterms_prompt:
        rate += assemblyai_keyterms_addon_per_hour_usd(settings)
    return rate / Decimal("3600")


#: USD/minuto, verificados en https://deepgram.com/pricing (Pay As You Go,
#: 2026-08-11). Nova-3 monolingüe (español, un único idioma por petición
#: — no el precio "multilingual", que no usamos).
DEEPGRAM_NOVA3_MONOLINGUAL_PRICE_PER_MINUTE_USD = Decimal("0.0077")
#: USD/minuto, add-ons — se suman aditivamente. `smart_format` está
#: incluido sin coste adicional (no aparece aquí a propósito).
DEEPGRAM_DIARIZATION_ADDON_PER_MINUTE_USD = Decimal("0.0020")
DEEPGRAM_KEYTERM_ADDON_PER_MINUTE_USD = Decimal("0.0012")

_DEEPGRAM_PROVIDER_NAMES = frozenset(
    {"deepgram", "deepgram_nova3_baseline", "deepgram_nova3_keyterms"}
)


def deepgram_base_price_per_minute_usd(settings: Settings) -> Decimal:
    return (
        settings.deepgram_price_per_minute_usd
        if settings.deepgram_price_per_minute_usd is not None
        else DEEPGRAM_NOVA3_MONOLINGUAL_PRICE_PER_MINUTE_USD
    )


def deepgram_diarization_addon_per_minute_usd(settings: Settings) -> Decimal:
    return (
        settings.deepgram_diarization_addon_per_minute_usd
        if settings.deepgram_diarization_addon_per_minute_usd is not None
        else DEEPGRAM_DIARIZATION_ADDON_PER_MINUTE_USD
    )


def deepgram_keyterm_addon_per_minute_usd(settings: Settings) -> Decimal:
    return (
        settings.deepgram_keyterm_addon_per_minute_usd
        if settings.deepgram_keyterm_addon_per_minute_usd is not None
        else DEEPGRAM_KEYTERM_ADDON_PER_MINUTE_USD
    )


def _deepgram_price_per_second_usd(
    settings: Settings, *, diarization: bool, keyterms_prompt: bool
) -> Decimal:
    rate_per_minute = deepgram_base_price_per_minute_usd(settings)
    if diarization:
        rate_per_minute += deepgram_diarization_addon_per_minute_usd(settings)
    if keyterms_prompt:
        rate_per_minute += deepgram_keyterm_addon_per_minute_usd(settings)
    return rate_per_minute / Decimal("60")


def price_per_second_usd(
    provider: str,
    model: str | None,
    settings: Settings,
    *,
    diarization: bool = False,
    medical_mode: bool = False,
    keyterms_prompt: bool = False,
) -> Decimal | None:
    """`None` si `provider` no es un proveedor con pricing conocido — el
    llamador decide qué hacer (`PricingTableAudioCostEstimator` devuelve
    coste 0). Despacha a la tabla de precios del proveedor correcto —
    AssemblyAI y Deepgram nunca comparten fórmula ni cifra."""
    if provider in _ASSEMBLYAI_PROVIDER_NAMES:
        return _assemblyai_price_per_second_usd(
            model,
            settings,
            diarization=diarization,
            medical_mode=medical_mode,
            keyterms_prompt=keyterms_prompt,
        )
    if provider in _DEEPGRAM_PROVIDER_NAMES:
        # Medical Mode no existe en Deepgram — se ignora silenciosamente
        # si se pasa (nunca aplicable a este proveedor).
        return _deepgram_price_per_second_usd(
            settings, diarization=diarization, keyterms_prompt=keyterms_prompt
        )
    return None
