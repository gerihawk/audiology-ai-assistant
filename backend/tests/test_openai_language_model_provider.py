"""Tests de OpenAILanguageModelProvider. Nunca llama a la API real: todo
el transporte HTTP se sustituye por httpx.MockTransport."""

from __future__ import annotations

import contextlib
import json

import httpx
import pytest

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import RenderedPrompt
from app.integrations.providers.openai_language_model_provider import (
    OpenAILanguageModelProvider,
    OpenAIResponseError,
)

_PROMPT = RenderedPrompt(system="Eres un asistente clínico.", user="Resume: hola.")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.openai.com/v1"
    )


def test_constructor_exige_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAILanguageModelProvider(api_key=None)


async def test_complete_exige_model():
    provider = OpenAILanguageModelProvider(api_key="test-key")
    with pytest.raises(ValueError, match="requiere 'model'"):
        await provider.complete(_PROMPT)


async def test_success_envia_headers_correctos_y_devuelve_texto_y_usage():
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": '{"text": "resumen generado"}'}
                        ],
                    }
                ],
                "usage": {"input_tokens": 30, "output_tokens": 12, "total_tokens": 42},
            },
        )

    provider = OpenAILanguageModelProvider(
        api_key="clave-ficticia-de-test", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gpt-5.2")

    assert result.text == '{"text": "resumen generado"}'
    assert result.input_tokens == 30
    assert result.output_tokens == 12

    request = seen["request"]
    assert request.url.path == "/v1/responses"
    assert request.headers["authorization"] == "Bearer clave-ficticia-de-test"

    body = json.loads(request.content)
    assert body["input"][0]["role"] == "developer"
    assert body["input"][1]["role"] == "user"


async def test_structured_output_envia_text_format():
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={"output": [{"type": "message", "role": "assistant", "content": []}]},
        )

    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    # Respuesta vacía a propósito — solo interesa el payload enviado.
    with contextlib.suppress(TransientProviderError):
        await provider.complete(_PROMPT, model="gpt-5.2", response_json_schema=schema)

    body = json.loads(seen["body"])
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"] == schema


async def test_ignora_tool_calls_y_extrae_el_primer_mensaje_assistant_con_texto():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "reasoning", "content": []},
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "respuesta real"}],
                    },
                ]
            },
        )

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gpt-5.2")
    assert result.text == "respuesta real"


async def test_timeout_se_traduce_en_transient_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tiempo agotado (fixture de test)")

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gpt-5.2")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_TIMEOUT


async def test_429_se_traduce_en_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gpt-5.2")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_RATE_LIMITED


async def test_5xx_se_traduce_en_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gpt-5.2")
    assert exc_info.value.reason == AIGenerationFailureReason.PROVIDER_UNAVAILABLE


async def test_otro_4xx_no_se_convierte_en_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(OpenAIResponseError):
        await provider.complete(_PROMPT, model="gpt-5.2")


async def test_respuesta_malformada_se_traduce_en_invalid_response_format():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = OpenAILanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gpt-5.2")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_api_key_nunca_aparece_en_una_excepcion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = OpenAILanguageModelProvider(
        api_key="secreto-super-sensible", http_client=_client_with_handler(handler)
    )
    with pytest.raises(OpenAIResponseError) as exc_info:
        await provider.complete(_PROMPT, model="gpt-5.2")
    assert "secreto-super-sensible" not in str(exc_info.value)
