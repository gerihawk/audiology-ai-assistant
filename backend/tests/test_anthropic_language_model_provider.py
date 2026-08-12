"""Tests de AnthropicLanguageModelProvider. Nunca llama a la API real:
todo el transporte HTTP se sustituye por httpx.MockTransport (encargo
Fase 6.3: "tests de proveedores siempre con HTTP simulado")."""

from __future__ import annotations

import httpx
import pytest

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import RenderedPrompt
from app.integrations.providers.anthropic_language_model_provider import (
    AnthropicLanguageModelProvider,
    AnthropicResponseError,
)

_PROMPT = RenderedPrompt(system="Eres un asistente clínico.", user="Resume: hola.")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.anthropic.com"
    )


def test_constructor_exige_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicLanguageModelProvider(api_key=None)


async def test_complete_exige_model():
    provider = AnthropicLanguageModelProvider(api_key="test-key")
    with pytest.raises(ValueError, match="requiere 'model'"):
        await provider.complete(_PROMPT)


async def test_success_envia_headers_correctos_y_devuelve_texto_y_usage():
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"text": "resumen generado"}'}],
                "usage": {"input_tokens": 42, "output_tokens": 17},
            },
        )

    provider = AnthropicLanguageModelProvider(
        api_key="clave-ficticia-de-test", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="claude-opus-5")

    assert result.text == '{"text": "resumen generado"}'
    assert result.input_tokens == 42
    assert result.output_tokens == 17

    request = seen["request"]
    assert request.url.path == "/v1/messages"
    assert request.headers["x-api-key"] == "clave-ficticia-de-test"
    assert request.headers["anthropic-version"] == "2023-06-01"


async def test_structured_output_envia_output_config_format():
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})

    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    await provider.complete(_PROMPT, model="claude-opus-5", response_json_schema=schema)

    import json

    body = json.loads(seen["body"])
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"] == schema


async def test_timeout_se_traduce_en_transient_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tiempo agotado (fixture de test)")

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_TIMEOUT


async def test_429_se_traduce_en_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_RATE_LIMITED


async def test_5xx_se_traduce_en_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_UNAVAILABLE


async def test_otro_4xx_no_se_convierte_en_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid x-api-key")

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(AnthropicResponseError):
        await provider.complete(_PROMPT, model="claude-opus-5")


async def test_respuesta_malformada_se_traduce_en_invalid_response_format():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_json_invalido_se_traduce_en_invalid_response_format():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"esto no es JSON")

    provider = AnthropicLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_api_key_nunca_aparece_en_una_excepcion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = AnthropicLanguageModelProvider(
        api_key="secreto-super-sensible", http_client=_client_with_handler(handler)
    )
    with pytest.raises(AnthropicResponseError) as exc_info:
        await provider.complete(_PROMPT, model="claude-opus-5")
    assert "secreto-super-sensible" not in str(exc_info.value)
