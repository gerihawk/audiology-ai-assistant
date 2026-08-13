"""Tests de GoogleLanguageModelProvider. Nunca llama a la API real: todo
el transporte HTTP se sustituye por httpx.MockTransport.

El fixture `_REAL_RESPONSE_SHAPE` reproduce, campo a campo, la respuesta
real (200) observada en la única llamada diagnóstica autorizada el
2026-08-13 (prompt sintético, sin datos clínicos) — claves de nivel
superior (`created, id, model, object, service_tier, status, steps,
updated, usage`) y valores reales de `usage`
(47 + 16 + 195 == 258, aritmética aditiva/disjunta confirmada). El texto
del `model_output` en el fixture es sintético (no es el texto real
devuelto), ya que solo la estructura y los números de `usage` son
relevantes para estos tests.
"""

from __future__ import annotations

import copy
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

_REAL_RESPONSE_SHAPE = {
    "created": 1755043200,
    "id": "interaction-fixture-id",
    "model": "gemini-3.6-flash",
    "object": "interaction",
    "service_tier": "standard",
    "status": "completed",
    "steps": [
        {
            "type": "thought",
            "content": [{"type": "text", "text": "razonamiento interno, nunca debe aparecer"}],
        },
        {
            "type": "tool_use",
            "content": [{"type": "text", "text": "llamada a herramienta, nunca debe aparecer"}],
        },
        {
            "type": "model_output",
            "content": [
                {"type": "text", "text": "Señal que "},
                {"type": "text", "text": "requiere valoración profesional."},
            ],
        },
    ],
    "usage": {
        "total_tokens": 258,
        "total_input_tokens": 47,
        "input_tokens_by_modality": [{"modality": "TEXT", "token_count": 47}],
        "total_cached_tokens": 0,
        "total_output_tokens": 16,
        "total_tool_use_tokens": 0,
        "total_thought_tokens": 195,
        "raw_prompt_token": 132,
    },
    "updated": 1755043201,
}


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://generativelanguage.googleapis.com"
    )


def _provider_for(
    body: dict, *, api_key: str = "clave-ficticia-de-test"
) -> GoogleLanguageModelProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return GoogleLanguageModelProvider(api_key=api_key, http_client=_client_with_handler(handler))


def test_constructor_exige_api_key():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GoogleLanguageModelProvider(api_key=None)


async def test_complete_exige_model():
    provider = GoogleLanguageModelProvider(api_key="test-key")
    with pytest.raises(ValueError, match="requiere 'model'"):
        await provider.complete(_PROMPT)


async def test_max_output_tokens_configurado_en_constructor_se_envia_en_el_payload():
    # Fase 6.3, auditoría 2026-08-13: antes de esta corrección, este
    # adapter nunca enviaba ningún techo de tokens de salida — el
    # preflight de coste asumía un peor caso que el provider no estaba
    # obligado a respetar. En producción siempre es
    # `settings.llm_max_output_tokens_estimate` vía factory.py — ver
    # test_language_model_provider_factory.py.
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json=_REAL_RESPONSE_SHAPE)

    provider = GoogleLanguageModelProvider(
        api_key="test-key", max_output_tokens=777, http_client=_client_with_handler(handler)
    )
    await provider.complete(_PROMPT, model="gemini-3.6-flash")

    body = json.loads(seen["body"])
    assert body["generation_config"]["max_output_tokens"] == 777


async def test_success_extrae_texto_de_steps_model_output_y_envia_headers_correctos():
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json=_REAL_RESPONSE_SHAPE)

    provider = GoogleLanguageModelProvider(
        api_key="clave-ficticia-de-test", http_client=_client_with_handler(handler)
    )
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")

    # Test 1 (extracción correcta) + Test 4 (concatenación multi-bloque):
    # los dos bloques `text` del único step `model_output` se concatenan
    # sin separador, en orden.
    assert result.text == "Señal que requiere valoración profesional."

    request = seen["request"]
    assert request.url.path == "/v1beta/interactions"
    assert request.headers["x-goog-api-key"] == "clave-ficticia-de-test"

    body = json.loads(request.content)
    assert body["system_instruction"] == "Eres un asistente clínico."
    assert body["input"] == "Resume: hola."


async def test_ignora_steps_de_tipo_thought_y_tool_use():
    # Test 2 + 3: el fixture incluye steps `thought` y `tool_use` antes del
    # `model_output` — su contenido nunca debe aparecer en el texto.
    provider = _provider_for(_REAL_RESPONSE_SHAPE)
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert "razonamiento interno" not in result.text
    assert "llamada a herramienta" not in result.text
    assert "nunca debe aparecer" not in result.text


async def test_usage_usa_los_nombres_de_campo_oficiales():
    # Test 5 + 6: `usage.total_input_tokens` / `usage.total_output_tokens`
    # de la Interactions API — nunca `input_tokens`/`output_tokens` sueltos
    # ni `usage_metadata.prompt_token_count`/`candidates_token_count`
    # (candidatos especulativos descartados, sin base documental).
    provider = _provider_for(_REAL_RESPONSE_SHAPE)
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert result.input_tokens == 47
    assert result.output_tokens == 16


async def test_thought_tokens_se_exponen_por_separado_en_reasoning_tokens():
    # Test 7: `usage.total_thought_tokens` (195) se expone en
    # `reasoning_tokens`, nunca sumado a `output_tokens` — la aritmética
    # 47 + 16 + 195 == 258 solo se sostiene si son contadores disjuntos
    # (ver docstring de `LanguageModelResponse.reasoning_tokens`).
    provider = _provider_for(_REAL_RESPONSE_SHAPE)
    result = await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert result.reasoning_tokens == 195
    assert result.output_tokens == 16
    assert result.input_tokens + result.output_tokens + result.reasoning_tokens == 258


async def test_structured_output_envia_response_format():
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json=_REAL_RESPONSE_SHAPE)

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


async def test_sin_steps_devuelve_invalid_response_format():
    body = copy.deepcopy(_REAL_RESPONSE_SHAPE)
    del body["steps"]
    provider = _provider_for(body)
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_sin_step_model_output_devuelve_invalid_response_format():
    # Test 8: ningún step de tipo `model_output` presente.
    body = copy.deepcopy(_REAL_RESPONSE_SHAPE)
    body["steps"] = [step for step in body["steps"] if step["type"] != "model_output"]
    provider = _provider_for(body)
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_model_output_sin_bloques_de_texto_devuelve_invalid_response_format():
    # Test 9: step `model_output` presente pero sin bloques `type == "text"`.
    body = copy.deepcopy(_REAL_RESPONSE_SHAPE)
    body["steps"] = [step for step in body["steps"] if step["type"] != "model_output"] + [
        {"type": "model_output", "content": [{"type": "image", "data": "..."}]}
    ]
    provider = _provider_for(body)
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_estructura_malformada_devuelve_invalid_response_format():
    # Test 10: `steps` no es una lista.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = GoogleLanguageModelProvider(
        api_key="test-key", http_client=_client_with_handler(handler)
    )
    with pytest.raises(TransientProviderError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert exc_info.value.reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT


async def test_api_key_nunca_aparece_en_una_excepcion():
    # Test 11.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = GoogleLanguageModelProvider(
        api_key="secreto-super-sensible", http_client=_client_with_handler(handler)
    )
    with pytest.raises(GoogleResponseError) as exc_info:
        await provider.complete(_PROMPT, model="gemini-3.6-flash")
    assert "secreto-super-sensible" not in str(exc_info.value)
