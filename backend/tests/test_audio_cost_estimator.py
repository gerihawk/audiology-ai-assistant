"""Tests de AudioCostEstimator: MockAudioCostEstimator y
PricingTableAudioCostEstimator, incluido el cálculo por componentes
(Fase 5.2: modelo base + diarización/Medical Mode/keyterms) — nunca
facturación autoritativa, ver docs/transcription-benchmark.md §Pricing."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings
from app.integrations.domain.audio_cost_estimator import CostEstimateSource
from app.integrations.factory import AUDIO_COST_ESTIMATOR_FACTORIES, build_audio_cost_estimator
from app.integrations.mocks.mock_audio_cost_estimator import MockAudioCostEstimator
from app.integrations.pricing import (
    ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD,
    DEEPGRAM_NOVA3_MONOLINGUAL_PRICE_PER_MINUTE_USD,
    PRICING_EFFECTIVE_DATE,
    PRICING_VERSION,
    assemblyai_base_price_per_hour_usd,
    assemblyai_diarization_addon_per_hour_usd,
    assemblyai_medical_mode_addon_per_hour_usd,
    deepgram_base_price_per_minute_usd,
    deepgram_diarization_addon_per_minute_usd,
)
from app.integrations.providers.pricing_table_audio_cost_estimator import (
    PricingTableAudioCostEstimator,
)


def _settings(**overrides) -> Settings:
    base = {"postgres_user": "test", "postgres_password": "test", "postgres_db": "test"}
    base.update(overrides)
    return Settings(**base)


def test_mock_siempre_devuelve_cero():
    estimate = MockAudioCostEstimator().estimate(
        provider="assemblyai", model=None, audio_duration_seconds=3600
    )
    assert estimate.amount_usd == Decimal("0")
    assert estimate.source == CostEstimateSource.MOCK
    assert estimate.pricing_version is None
    assert estimate.pricing_effective_date is None


def test_mock_ignora_los_componentes_activos_sin_fallar():
    estimate = MockAudioCostEstimator().estimate(
        provider="assemblyai",
        model="universal-3-5-pro",
        audio_duration_seconds=3600,
        diarization=True,
        medical_mode=True,
        keyterms_prompt=True,
    )
    assert estimate.amount_usd == Decimal("0")


def test_pricing_table_calcula_proporcional_a_la_duracion():
    settings = _settings(
        assemblyai_price_per_hour_usd=Decimal("3600")
    )  # $1/segundo, fácil de verificar
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(provider="assemblyai", model=None, audio_duration_seconds=115)

    assert estimate.amount_usd == Decimal("115")
    assert estimate.source == CostEstimateSource.PRICING_TABLE


def test_pricing_table_incluye_version_y_fecha():
    settings = _settings()
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(provider="assemblyai", model=None, audio_duration_seconds=60)

    assert estimate.pricing_version == PRICING_VERSION
    assert estimate.pricing_effective_date == PRICING_EFFECTIVE_DATE


def test_precio_base_usa_el_configurado_si_existe():
    settings = _settings(assemblyai_price_per_hour_usd=Decimal("1.0"))
    assert assemblyai_base_price_per_hour_usd(settings, None) == Decimal("1.0")


def test_precio_base_usa_universal_2_por_defecto_sin_modelo_explicito():
    settings = _settings(assemblyai_price_per_hour_usd=None)
    price = assemblyai_base_price_per_hour_usd(settings, None)
    assert price == ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD["universal-2"]


def test_precio_base_usa_universal_3_5_pro_si_ese_es_el_modelo():
    settings = _settings(assemblyai_price_per_hour_usd=None)
    price = assemblyai_base_price_per_hour_usd(settings, "universal-3-5-pro")
    assert price == ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD["universal-3-5-pro"]
    assert (
        price > ASSEMBLYAI_BASE_PRICE_PER_HOUR_USD["universal-2"]
    )  # más caro, verificado en pricing oficial


def test_pricing_table_proveedor_desconocido_devuelve_cero():
    settings = _settings()
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(provider="speechmatics", model=None, audio_duration_seconds=100)

    assert estimate.amount_usd == Decimal("0")


# --- Coste por componentes (Fase 5.2) -------------------------------------------


def test_baseline_sin_componentes_activos_usa_solo_el_precio_base():
    settings = _settings(assemblyai_price_per_hour_usd=Decimal("3600"))  # $1/s
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(
        provider="assemblyai_baseline", model=None, audio_duration_seconds=10
    )

    assert estimate.amount_usd == Decimal("10")  # solo precio base, sin add-ons


def test_diarizacion_anade_su_addon():
    settings = _settings(
        assemblyai_price_per_hour_usd=Decimal("3600"),
        assemblyai_diarization_addon_per_hour_usd=Decimal("360"),  # +$0.1/s
    )
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(
        provider="assemblyai_baseline", model=None, audio_duration_seconds=10, diarization=True
    )

    assert estimate.amount_usd == Decimal("11")  # (1 + 0.1) * 10


def test_perfil_optimizado_suma_todos_los_addons_activos():
    settings = _settings(
        assemblyai_price_per_hour_usd=Decimal("3600"),  # $1/s base
        assemblyai_diarization_addon_per_hour_usd=Decimal("360"),  # +$0.1/s
        assemblyai_medical_mode_addon_per_hour_usd=Decimal("720"),  # +$0.2/s
        assemblyai_keyterms_addon_per_hour_usd=Decimal("1800"),  # +$0.5/s
    )
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(
        provider="assemblyai_optimized",
        model="universal-3-5-pro",
        audio_duration_seconds=10,
        diarization=True,
        medical_mode=True,
        keyterms_prompt=True,
    )

    # (1 + 0.1 + 0.2 + 0.5) * 10 = 18
    assert estimate.amount_usd == Decimal("18")


def test_optimizado_es_mas_caro_que_baseline_con_los_mismos_precios():
    settings = _settings()  # precios reales por defecto (verificados, ver pricing.py)
    estimator = PricingTableAudioCostEstimator(settings)

    baseline = estimator.estimate(
        provider="assemblyai_baseline",
        model=None,
        audio_duration_seconds=3600,
        diarization=True,
    )
    optimized = estimator.estimate(
        provider="assemblyai_optimized",
        model="universal-3-5-pro",
        audio_duration_seconds=3600,
        diarization=True,
        medical_mode=True,
        keyterms_prompt=True,
    )

    assert optimized.amount_usd > baseline.amount_usd


def test_addons_usan_el_valor_configurado_si_existe():
    settings = _settings(assemblyai_diarization_addon_per_hour_usd=Decimal("99"))
    assert assemblyai_diarization_addon_per_hour_usd(settings) == Decimal("99")


def test_addons_usan_el_valor_por_defecto_si_no_se_configuran():
    settings = _settings()
    assert assemblyai_medical_mode_addon_per_hour_usd(settings) > Decimal("0")


# --- Deepgram (Fase 5.3) — pricing independiente, nunca mezclado con AssemblyAI ---


def test_deepgram_precio_base_usa_el_valor_por_defecto():
    settings = _settings()
    assert (
        deepgram_base_price_per_minute_usd(settings)
        == DEEPGRAM_NOVA3_MONOLINGUAL_PRICE_PER_MINUTE_USD
    )


def test_deepgram_precio_base_usa_el_configurado_si_existe():
    settings = _settings(deepgram_price_per_minute_usd=Decimal("1.0"))
    assert deepgram_base_price_per_minute_usd(settings) == Decimal("1.0")


def test_deepgram_addon_diarizacion_usa_el_valor_por_defecto():
    settings = _settings()
    assert deepgram_diarization_addon_per_minute_usd(settings) > Decimal("0")


def test_deepgram_diarizacion_anade_su_addon():
    settings = _settings(
        deepgram_price_per_minute_usd=Decimal("60"),  # $1/s
        deepgram_diarization_addon_per_minute_usd=Decimal("6"),  # +$0.1/s
    )
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(
        provider="deepgram_nova3_baseline",
        model="nova-3",
        audio_duration_seconds=10,
        diarization=True,
    )

    assert estimate.amount_usd == Decimal("11")  # (1 + 0.1) * 10


def test_deepgram_medical_mode_se_ignora_silenciosamente_no_existe_en_deepgram():
    settings = _settings(deepgram_price_per_minute_usd=Decimal("60"))
    estimator = PricingTableAudioCostEstimator(settings)

    con_medical_mode = estimator.estimate(
        provider="deepgram_nova3_baseline",
        model="nova-3",
        audio_duration_seconds=10,
        medical_mode=True,  # no existe en Deepgram — no debe sumar nada
    )
    sin_medical_mode = estimator.estimate(
        provider="deepgram_nova3_baseline", model="nova-3", audio_duration_seconds=10
    )

    assert con_medical_mode.amount_usd == sin_medical_mode.amount_usd


def test_deepgram_y_assemblyai_nunca_comparten_tabla_de_precios():
    settings = _settings(
        assemblyai_price_per_hour_usd=Decimal("360"),  # $0.1/s
        deepgram_price_per_minute_usd=Decimal("60"),  # $1/s — deliberadamente distinto
    )
    estimator = PricingTableAudioCostEstimator(settings)

    assemblyai_estimate = estimator.estimate(
        provider="assemblyai_baseline", model=None, audio_duration_seconds=10
    )
    deepgram_estimate = estimator.estimate(
        provider="deepgram_nova3_baseline", model="nova-3", audio_duration_seconds=10
    )

    assert assemblyai_estimate.amount_usd == Decimal("1")
    assert deepgram_estimate.amount_usd == Decimal("10")


def test_deepgram_incluye_version_y_fecha_de_pricing():
    settings = _settings()
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(
        provider="deepgram_nova3_baseline", model="nova-3", audio_duration_seconds=60
    )

    assert estimate.pricing_version == PRICING_VERSION
    assert estimate.pricing_effective_date == PRICING_EFFECTIVE_DATE
    assert estimate.source == CostEstimateSource.PRICING_TABLE


# --- Factory ---------------------------------------------------------------------


def test_factory_resuelve_mock_para_mock():
    settings = _settings(transcription_provider="mock")
    estimator = build_audio_cost_estimator(settings)
    assert isinstance(estimator, MockAudioCostEstimator)


def test_factory_resuelve_pricing_table_para_assemblyai():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key="clave-test")
    estimator = build_audio_cost_estimator(settings)
    assert isinstance(estimator, PricingTableAudioCostEstimator)


def test_factory_resuelve_pricing_table_para_cada_perfil():
    settings = _settings()
    assert isinstance(
        build_audio_cost_estimator(settings, "assemblyai_baseline"), PricingTableAudioCostEstimator
    )
    assert isinstance(
        build_audio_cost_estimator(settings, "assemblyai_optimized"), PricingTableAudioCostEstimator
    )


def test_factory_provider_name_explicito_no_depende_de_settings():
    settings = _settings(transcription_provider="mock")
    estimator = build_audio_cost_estimator(settings, "assemblyai")
    assert isinstance(estimator, PricingTableAudioCostEstimator)


def test_factory_proveedor_no_registrado_no_lanza_devuelve_mock():
    settings = _settings()
    estimator = build_audio_cost_estimator(settings, "speechmatics")
    assert isinstance(estimator, MockAudioCostEstimator)


def test_factory_resuelve_pricing_table_para_deepgram():
    settings = _settings(transcription_provider="deepgram", deepgram_api_key="clave-test")
    estimator = build_audio_cost_estimator(settings)
    assert isinstance(estimator, PricingTableAudioCostEstimator)


def test_factory_resuelve_pricing_table_para_cada_perfil_deepgram():
    settings = _settings()
    assert isinstance(
        build_audio_cost_estimator(settings, "deepgram_nova3_baseline"),
        PricingTableAudioCostEstimator,
    )
    assert isinstance(
        build_audio_cost_estimator(settings, "deepgram_nova3_keyterms"),
        PricingTableAudioCostEstimator,
    )


def test_registro_expone_los_proveedores_y_perfiles_soportados():
    assert set(AUDIO_COST_ESTIMATOR_FACTORIES) == {
        "mock",
        "assemblyai",
        "assemblyai_baseline",
        "assemblyai_optimized",
        "deepgram",
        "deepgram_nova3_baseline",
        "deepgram_nova3_keyterms",
    }
