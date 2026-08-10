"""Tests de AudioCostEstimator: MockAudioCostEstimator y
PricingTableAudioCostEstimator (nunca facturación autoritativa, ver
docs/transcription-benchmark.md §Pricing)."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings
from app.integrations.domain.audio_cost_estimator import CostEstimateSource
from app.integrations.factory import AUDIO_COST_ESTIMATOR_FACTORIES, build_audio_cost_estimator
from app.integrations.mocks.mock_audio_cost_estimator import MockAudioCostEstimator
from app.integrations.pricing import (
    PRICING_EFFECTIVE_DATE,
    PRICING_VERSION,
    assemblyai_price_per_hour_usd,
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


def test_pricing_table_usa_el_precio_configurado_si_existe():
    settings = _settings(assemblyai_price_per_hour_usd=Decimal("1.0"))
    assert assemblyai_price_per_hour_usd(settings) == Decimal("1.0")


def test_pricing_table_usa_el_precio_por_defecto_si_no_se_configura():
    settings = _settings(assemblyai_price_per_hour_usd=None)
    price = assemblyai_price_per_hour_usd(settings)
    assert price > Decimal("0")


def test_pricing_table_proveedor_desconocido_devuelve_cero():
    settings = _settings()
    estimator = PricingTableAudioCostEstimator(settings)

    estimate = estimator.estimate(provider="deepgram", model=None, audio_duration_seconds=100)

    assert estimate.amount_usd == Decimal("0")


def test_factory_resuelve_mock_para_mock():
    settings = _settings(transcription_provider="mock")
    estimator = build_audio_cost_estimator(settings)
    assert isinstance(estimator, MockAudioCostEstimator)


def test_factory_resuelve_pricing_table_para_assemblyai():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key="clave-test")
    estimator = build_audio_cost_estimator(settings)
    assert isinstance(estimator, PricingTableAudioCostEstimator)


def test_factory_provider_name_explicito_no_depende_de_settings():
    settings = _settings(transcription_provider="mock")
    estimator = build_audio_cost_estimator(settings, "assemblyai")
    assert isinstance(estimator, PricingTableAudioCostEstimator)


def test_factory_proveedor_no_registrado_no_lanza_devuelve_mock():
    settings = _settings()
    estimator = build_audio_cost_estimator(settings, "deepgram")
    assert isinstance(estimator, MockAudioCostEstimator)


def test_registro_expone_los_proveedores_soportados():
    assert set(AUDIO_COST_ESTIMATOR_FACTORIES) == {"mock", "assemblyai"}
