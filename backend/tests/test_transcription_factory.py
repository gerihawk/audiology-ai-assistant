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
    with pytest.raises(ValueError, match="deepgram"):
        build_transcription_provider(settings, "deepgram")


def test_el_registro_expone_todos_los_proveedores_soportados():
    assert set(TRANSCRIPTION_PROVIDER_FACTORIES) == {"mock", "assemblyai"}


def test_provider_name_explicito_ignora_transcription_provider_de_settings():
    settings = _settings(transcription_provider="assemblyai", assemblyai_api_key="clave-test")
    provider = build_transcription_provider(settings, "mock")
    assert isinstance(provider, MockTranscriptionProvider)
