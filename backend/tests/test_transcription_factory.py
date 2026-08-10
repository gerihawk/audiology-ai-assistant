"""Tests de la factoría de selección de TranscriptionProvider por configuración."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.integrations.factory import (
    TRANSCRIPTION_PROVIDER_FACTORIES,
    build_transcription_provider,
)
from app.integrations.mocks.mock_transcription_provider import MockTranscriptionProvider
from app.integrations.providers.assemblyai_transcription_provider import (
    AssemblyAITranscriptionProvider,
)
from app.integrations.providers.deepgram_transcription_provider import (
    DeepgramTranscriptionProvider,
)


def _settings(**overrides) -> Settings:
    # `transcription_provider`/`assemblyai_api_key` se fijan explícitamente:
    # el entorno real (docker-compose, .env) puede tener
    # TRANSCRIPTION_PROVIDER=assemblyai configurado para desarrollo, y
    # estos tests deben ser deterministas independientemente de eso.
    base = {
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "transcription_provider": "mock",
        "assemblyai_api_key": None,
    }
    base.update(overrides)
    return Settings(**base)


def test_mock_es_el_valor_por_defecto():
    provider = build_transcription_provider(_settings())
    assert isinstance(provider, MockTranscriptionProvider)


def test_resuelve_assemblyai_con_api_key():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key="clave-test")
    provider = build_transcription_provider(settings)
    assert isinstance(provider, AssemblyAITranscriptionProvider)


def test_assemblyai_sin_api_key_lanza_error_claro():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key=None)
    with pytest.raises(ValueError, match="ASSEMBLYAI_API_KEY"):
        build_transcription_provider(settings)


def test_proveedor_desconocido_lanza_error_claro():
    settings = _settings()
    with pytest.raises(ValueError, match="speechmatics"):
        build_transcription_provider(settings, "speechmatics")


def test_el_registro_expone_todos_los_proveedores_y_perfiles_soportados():
    assert set(TRANSCRIPTION_PROVIDER_FACTORIES) == {
        "mock",
        "assemblyai",
        "assemblyai_baseline",
        "assemblyai_optimized",
        "deepgram",
        "deepgram_nova3_baseline",
        "deepgram_nova3_keyterms",
    }


def test_provider_name_explicito_ignora_transcription_provider_de_settings():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key="clave-test")
    provider = build_transcription_provider(settings, "mock")
    assert isinstance(provider, MockTranscriptionProvider)


# --- Perfiles assemblyai_baseline / assemblyai_optimized (Fase 5.2) ------------


def test_assemblyai_baseline_es_identico_a_assemblyai():
    settings = _settings(assemblyai_api_key="clave-test")
    baseline = build_transcription_provider(settings, "assemblyai_baseline")
    produccion = build_transcription_provider(settings, "assemblyai")

    assert isinstance(baseline, AssemblyAITranscriptionProvider)
    assert baseline._speech_models is None
    assert baseline._speakers_expected is None
    assert baseline._medical_mode is False
    assert baseline._keyterms_prompt is None
    # Misma construcción que el perfil de producción, no una casualidad.
    assert produccion._speech_models is None
    assert produccion._medical_mode is False


def test_assemblyai_optimized_aplica_el_perfil_experimental_por_defecto():
    settings = _settings(assemblyai_api_key="clave-test")
    optimized = build_transcription_provider(settings, "assemblyai_optimized")

    assert isinstance(optimized, AssemblyAITranscriptionProvider)
    assert optimized._speech_models == ["universal-3-5-pro"]
    assert optimized._speakers_expected == 2
    assert optimized._medical_mode is True
    assert optimized._keyterms_prompt is not None
    assert len(optimized._keyterms_prompt) > 0
    assert optimized._keyterm_set_version == "audiology-es-v1"


def test_assemblyai_optimized_speakers_expected_null_es_configurable():
    settings = _settings(
        assemblyai_api_key="clave-test", assemblyai_optimized_speakers_expected=None
    )
    optimized = build_transcription_provider(settings, "assemblyai_optimized")

    assert optimized._speakers_expected is None


def test_assemblyai_optimized_keyterms_desactivables():
    settings = _settings(
        assemblyai_api_key="clave-test", assemblyai_optimized_keyterms_enabled=False
    )
    optimized = build_transcription_provider(settings, "assemblyai_optimized")

    assert optimized._keyterms_prompt is None
    assert optimized._keyterm_set_version is None


# --- Deepgram (Fase 5.3) --------------------------------------------------------


def test_resuelve_deepgram_con_api_key():
    settings = _settings(transcription_provider="deepgram", deepgram_api_key="clave-test")
    provider = build_transcription_provider(settings)
    assert isinstance(provider, DeepgramTranscriptionProvider)


def test_deepgram_sin_api_key_lanza_error_claro():
    settings = _settings(transcription_provider="deepgram", deepgram_api_key=None)
    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        build_transcription_provider(settings)


def test_deepgram_es_identico_a_deepgram_nova3_baseline():
    settings = _settings(deepgram_api_key="clave-test")
    produccion = build_transcription_provider(settings, "deepgram")
    baseline = build_transcription_provider(settings, "deepgram_nova3_baseline")

    assert isinstance(produccion, DeepgramTranscriptionProvider)
    assert produccion._model == "nova-3"
    assert produccion._keyterms is None
    assert baseline._model == "nova-3"
    assert baseline._keyterms is None


def test_deepgram_nova3_keyterms_no_se_llama_esta_fase_pero_esta_preparado():
    settings = _settings(deepgram_api_key="clave-test", deepgram_keyterms_enabled=True)
    keyterms_profile = build_transcription_provider(settings, "deepgram_nova3_keyterms")

    assert isinstance(keyterms_profile, DeepgramTranscriptionProvider)
    assert keyterms_profile._keyterms is not None
    assert len(keyterms_profile._keyterms) > 0
    assert keyterms_profile._keyterm_set_version == "audiology-es-v1"


def test_deepgram_endpoint_eu_por_defecto():
    settings = _settings(deepgram_api_key="clave-test")
    provider = build_transcription_provider(settings, "deepgram")
    assert "eu.deepgram.com" in provider._base_url
