"""Tests de GoogleLanguageModelProvider. Nunca llama a la API real: todo
el transporte HTTP se sustituye por httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import RenderedPrompt
from app.integrations.providers.google_language_model_provider import (
    GoogleLanguageModelProvider,
    GoogleResponseError,
)

_PROMPT = RenderedPrompt(system="Eres un asistente clínico.", user="Resume: hola.")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://generativelanguage.googleapis.com"
    )


def test_constructor_exige_api_key():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GoogleLanguageModelProvider(api_key=None)


async def test_complete_exige_model():
    provider = GoogleLanguageModelProvider(api_key="test-key")
    with pytest.raises(ValueError, match="requiere 'model'"):
        await provider.complete(_PROMPT)


async def test_success_envia_headers_correctos_y_devuelve_texto():
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "output_text": '{"text": "resumen generado"}',
                "usage": {"input_tokens": 25, "output_tokens": 9},
            },
        )

    provider = GoogleLanguageModelProvider(
        api_key="clave-ficticia-de-test", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")

    assert result.text == '{"text": "resumen generado"}'
    assert result.input_tokens == 25
    assert result.output_tokens == 9

    request = seen["request"]
    assert request.url.path == "/v1beta/interactions"
    assert request.headers["x-goog-api-key"] == "clave-ficticia-de-test"

    body = json.loads(request.content)
    assert body["system_instruction"] == "Eres un asistente clínico."
    assert body["input"] == "Resume: hola."


async def test_usage_metadata_alternativo_tambien_se_reconoce():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output_text": "texto",
                "usage_metadata": {"prompt_token_count": 11, "candidates_token_count": 4},
            },
        )

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert result.input_tokens == 11
    assert result.output_tokens == 4


async def test_sin_ningun_campo_de_usage_reconocido_devuelve_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output_text": "texto"})

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert result.input_tokens is None
    assert result.output_tokens is None


async def test_structured_output_envia_response_format():
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"output_text": "{}"})

    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    await provider.complete(_PROMPT, model="gemini-3.6-flash", response_json_schema=schema)

    body = json.loads(seen["body"])
    assert body["response_format"]["mime_type"] == "application/json"
    assert body["response_format"]["schema"] == schema


async def test_timeout_se_traduce_en_transient_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tiempo agotado (fixture de test)")

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_TIMEOUT


async def test_429_se_traduce_en_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_RATE_LIMITED


async def test_5xx_se_traduce_en_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_UNAVAILABLE


async def test_otro_4xx_no_se_convierte_en_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(GoogleResponseError):
        await provider.complete(_PROMPT, model="gemini-3.6-flash")


async def test_respuesta_malformada_se_traduce_en_invalid_response_format():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_api_key_nunca_aparece_en_una_excepcion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = GoogleLanguageModelProvider(
        api_key="secreto-super-sensible", http_client=_client_with_handler(handler)
    )
    with pytest.raises(GoogleResponseError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert "secreto-super-sensible" not in str(exc_info.value)
