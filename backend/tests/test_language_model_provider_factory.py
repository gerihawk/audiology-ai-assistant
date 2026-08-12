"""`build_language_model_provider` (Fase 6.3.4/6.3.5) — mismo patrón que
`build_transcription_provider`, sin llamadas de red. Construir un
proveedor real solo instancia el cliente (constructor), nunca hace una
petición HTTP — eso solo ocurre al llamar `.complete()`, que estos tests
nunca invocan."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.integrations.factory import (
    LANGUAGE_MODEL_PROVIDER_FACTORIES,
    build_language_model_provider,
)
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider
from app.integrations.providers.anthropic_language_model_provider import (
    AnthropicLanguageModelProvider,
)
from app.integrations.providers.google_language_model_provider import (
    GoogleLanguageModelProvider,
)
from app.integrations.providers.openai_language_model_provider import (
    OpenAILanguageModelProvider,
)


def _settings(**overrides) -> Settings:
    return Settings(
        postgres_user="user",
        postgres_password="s3cret",
        postgres_db="db",
        postgres_host="localhost",
        **overrides,
    )


def test_los_cuatro_proveedores_estan_registrados():
    assert set(LANGUAGE_MODEL_PROVIDER_FACTORIES) == {"mock", "anthropic", "openai", "google"}


def test_build_mock_devuelve_mock_language_model_provider():
    provider = build_language_model_provider(_settings(), "mock")
    assert isinstance(provider, MockLanguageModelProvider)


def test_build_anthropic_con_key_devuelve_el_provider_configurado():
    provider = build_language_model_provider(_settings(anthropic_api_key="test-key"), "anthropic")
    assert isinstance(provider, AnthropicLanguageModelProvider)


def test_build_anthropic_sin_key_falla_explicito():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_language_model_provider(_settings(), "anthropic")


def test_build_openai_con_key_devuelve_el_provider_configurado():
    provider = build_language_model_provider(_settings(openai_api_key="test-key"), "openai")
    assert isinstance(provider, OpenAILanguageModelProvider)


def test_build_openai_sin_key_falla_explicito():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_language_model_provider(_settings(), "openai")


def test_build_google_con_key_devuelve_el_provider_configurado():
    provider = build_language_model_provider(_settings(google_api_key="test-key"), "google")
    assert isinstance(provider, GoogleLanguageModelProvider)


def test_build_google_sin_key_falla_explicito():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        build_language_model_provider(_settings(), "google")


def test_proveedor_desconocido_lanza_value_error_explicito():
    with pytest.raises(ValueError, match="no es un proveedor de modelo de lenguaje reconocido"):
        build_language_model_provider(_settings(), "cohere")


def test_mensaje_de_error_lista_los_valores_validos():
    with pytest.raises(ValueError, match="anthropic"):
        build_language_model_provider(_settings(), "unknown")
