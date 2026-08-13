"""`build_language_model_provider` (Fase 6.3.4/6.3.5) — mismo patrón que
`build_transcription_provider`, sin llamadas de red. Construir un
proveedor real solo instancia el cliente (constructor), nunca hace una
petición HTTP — eso solo ocurre al llamar `.complete()`, que estos tests
nunca invocan."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.integrations.domain.language_model_provider import RenderedPrompt
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

_PROMPT = RenderedPrompt(system=None, user="hola")


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


# --- Fuente única de verdad del techo de tokens de salida (Fase 6.3,
# auditoría 2026-08-13) --------------------------------------------------
#
# `run_provider_step` calcula el peor caso del preflight de coste con
# `context.max_output_tokens_estimate` (= `Settings.llm_max_output_tokens_
# estimate`). Antes de esta corrección, cada provider real tenía su propio
# techo de tokens de salida independiente (Anthropic: `4096` fijo;
# OpenAI/Google: sin techo en absoluto) que podía divergir libremente de
# ese preflight — un bug de cost-safety real. Estos tests prueban que la
# factory pasa SIEMPRE `settings.llm_max_output_tokens_estimate` a los tres
# providers reales, y que ese valor llega intacto hasta el payload HTTP que
# se enviaría al provider — un cambio futuro que desconecte cualquiera de
# los dos debe romper uno de estos tests.


def test_factory_anthropic_usa_llm_max_output_tokens_estimate_como_max_tokens():
    settings = _settings(anthropic_api_key="test-key", llm_max_output_tokens_estimate=1234)
    provider = build_language_model_provider(settings, "anthropic")
    payload = provider._payload(_PROMPT, "claude-opus-5", None)
    assert payload["max_tokens"] == settings.llm_max_output_tokens_estimate == 1234


def test_factory_openai_usa_llm_max_output_tokens_estimate_como_max_output_tokens():
    settings = _settings(openai_api_key="test-key", llm_max_output_tokens_estimate=1234)
    provider = build_language_model_provider(settings, "openai")
    payload = provider._payload(_PROMPT, "gpt-5.2", None)
    assert payload["max_output_tokens"] == settings.llm_max_output_tokens_estimate == 1234


def test_factory_google_usa_llm_max_output_tokens_estimate_como_max_output_tokens():
    settings = _settings(google_api_key="test-key", llm_max_output_tokens_estimate=1234)
    provider = build_language_model_provider(settings, "google")
    payload = provider._payload(_PROMPT, "gemini-3.6-flash", None)
    assert (
        payload["generation_config"]["max_output_tokens"]
        == settings.llm_max_output_tokens_estimate
        == 1234
    )
