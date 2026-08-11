"""Tests de `BenchmarkLLMClient` — Fase 6.2. Nunca contacta
`openrouter.ai`: `httpx.AsyncClient` se construye con
`transport=httpx.MockTransport(handler)`, mismo patrón que
`tests/test_assemblyai_provider.py`/`tests/test_deepgram_provider.py`."""

from __future__ import annotations

import json

import httpx
import pytest

from benchmark.generation.openrouter_client import (
    BenchmarkLLMClient,
    LlmCompletionRequest,
    OpenRouterAuthenticationError,
    OpenRouterMalformedResponseError,
    OpenRouterProviderError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)

_REQUEST = LlmCompletionRequest(model="test/model", system_prompt="system", user_prompt="user")


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://openrouter.ai/api/v1"
    )


def _success_body(*, text: str = '{"text": "ok"}', cost: str | None = None) -> dict:
    body = {
        "model": "test/model",
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }
    if cost is not None:
        body["usage"]["cost"] = cost
    return body


class TestConstruction:
    def test_sin_api_key_falla_explicitamente(self):
        with pytest.raises(OpenRouterAuthenticationError):
            BenchmarkLLMClient(
                api_key=None, base_url="https://openrouter.ai/api/v1", timeout_seconds=30
            )

    def test_api_key_vacia_falla_explicitamente(self):
        with pytest.raises(OpenRouterAuthenticationError):
            BenchmarkLLMClient(
                api_key="", base_url="https://openrouter.ai/api/v1", timeout_seconds=30
            )


class TestComplete:
    async def test_respuesta_valida_se_parsea(self):
        seen_auth: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("authorization", ""))
            assert request.url.path == "/api/v1/chat/completions"
            payload = json.loads(request.content)
            assert payload["model"] == "test/model"
            assert payload["messages"] == [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ]
            return httpx.Response(200, json=_success_body())

        client = BenchmarkLLMClient(
            api_key="sk-test-secret",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        response = await client.complete(_REQUEST)

        assert response.raw_text == '{"text": "ok"}'
        assert response.input_tokens == 100
        assert response.output_tokens == 20
        assert response.provider_reported_cost_usd is None
        assert seen_auth == ["Bearer sk-test-secret"]

    async def test_coste_reportado_por_el_proveedor_se_expone_por_separado(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_success_body(cost="0.0012"))

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        response = await client.complete(_REQUEST)

        assert response.provider_reported_cost_usd == "0.0012"

    async def test_api_key_nunca_aparece_en_una_excepcion(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        client = BenchmarkLLMClient(
            api_key="sk-super-secreta",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterProviderError) as exc_info:
            await client.complete(_REQUEST)

        assert "sk-super-secreta" not in str(exc_info.value)

    async def test_json_malformado(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="esto no es JSON")

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterMalformedResponseError):
            await client.complete(_REQUEST)

    async def test_forma_de_respuesta_inesperada(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterMalformedResponseError):
            await client.complete(_REQUEST)

    async def test_rate_limited(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "rate limited"})

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterRateLimitError):
            await client.complete(_REQUEST)

    async def test_error_de_proveedor_5xx(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="service unavailable")

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterProviderError) as exc_info:
            await client.complete(_REQUEST)
        assert exc_info.value.status_code == 503

    async def test_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        with pytest.raises(OpenRouterTimeoutError):
            await client.complete(_REQUEST)

    async def test_structured_output_incluye_response_format(self):
        seen_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_payload.update(json.loads(request.content))
            return httpx.Response(200, json=_success_body())

        client = BenchmarkLLMClient(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            http_client=_client_with_handler(handler),
        )
        request = LlmCompletionRequest(
            model="test/model",
            system_prompt=None,
            user_prompt="user",
            response_json_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        await client.complete(request)

        assert seen_payload["response_format"]["type"] == "json_schema"
        assert seen_payload["messages"] == [{"role": "user", "content": "user"}]
