"""OpenAILanguageModelProvider: proveedor LLM directo real (Fase 6.3.5).

Verificado contra la documentación pública oficial vigente el 2026-08-12
(no de memoria, no por lo observado en OpenRouter — encargo Fase 6.3,
decisión #2). OpenAI ha migrado su superficie recomendada de "Chat
Completions" a la **Responses API** — se implementa contra esta última
por ser la actual y documentada como recomendada:

- Endpoint, auth y forma de request/response de la Responses API:
  https://developers.openai.com/api/docs/guides/migrate-to-responses
  https://developers.openai.com/api/docs/guides/text
- Instrucciones de sistema vía mensajes con `role: "developer"` dentro de
  `input` (no existe un campo `instructions` de nivel superior separado):
  https://developers.openai.com/api/docs/api-reference/responses/create
- Salida estructurada vía `text.format` (`type: "json_schema"`, migrado
  desde `response_format` de Chat Completions) y que `gpt-5.2` la soporta
  ("structured_outputs" listado en sus supported features):
  https://developers.openai.com/api/docs/models/gpt-5.2
- Forma del objeto `usage` (`input_tokens`/`output_tokens`/`total_tokens`,
  ya no `prompt_tokens`/`completion_tokens` de Chat Completions):
  https://developers.openai.com/api/docs/guides/token-counting
- Modelo `gpt-5.2` confirmado como id nativo exacto (misma cadena que el
  benchmark de OpenRouter, sin el prefijo `openai/`).

Ninguna llamada real se ha hecho contra esta API durante su
implementación. Usa `httpx` genérico, sin el SDK oficial de OpenAI — mismo
criterio que el resto de proveedores directos de este módulo.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt

_RESPONSES_PATH = "/responses"
#: Corrección Fase 6.3 (auditoría 2026-08-13): antes de esta corrección,
#: este adapter nunca enviaba ningún techo de tokens de salida a la
#: Responses API (a diferencia de Anthropic, donde `max_tokens` es
#: obligatorio) — el preflight de coste asumía un peor caso
#: (`llm_max_output_tokens_estimate`) que el provider no estaba obligado a
#: respetar en absoluto. `factory.py::build_language_model_provider`
#: SIEMPRE pasa `max_output_tokens=settings.llm_max_output_tokens_estimate`
#: — la misma fuente de verdad que usa `run_provider_step` para el
#: preflight. Este valor (2000) es solo el fallback para construcción
#: directa fuera de la factory (scripts/tests).
_DEFAULT_MAX_OUTPUT_TOKENS = 2000


class OpenAIResponseError(Exception):
    """Error HTTP 4xx (salvo 429) — nunca retryable automáticamente. Nunca
    incluye cabeceras (donde viajaría la API key)."""


class OpenAILanguageModelProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY es obligatoria para usar OpenAILanguageModelProvider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._injected_client = http_client

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _payload(
        self, prompt: RenderedPrompt, model: str, response_json_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        input_items: list[dict[str, Any]] = []
        if prompt.system is not None:
            input_items.append({"type": "message", "role": "developer", "content": prompt.system})
        input_items.append({"type": "message", "role": "user", "content": prompt.user})

        payload: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "max_output_tokens": self._max_output_tokens,
        }
        if response_json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "generation_output",
                    "strict": True,
                    "schema": response_json_schema,
                }
            }
        return payload

    async def complete(
        self,
        prompt: RenderedPrompt,
        *,
        model: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> LanguageModelResponse:
        if not model:
            raise ValueError("OpenAILanguageModelProvider.complete() requiere 'model'.")

        client = self._injected_client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        )
        owns_client = self._injected_client is None
        try:
            try:
                response = await client.post(
                    _RESPONSES_PATH,
                    headers=self._headers(),
                    json=self._payload(prompt, model, response_json_schema),
                )
            except httpx.TimeoutException as exc:
                raise TransientProviderError(
                    "Timeout esperando respuesta de OpenAI.",
                    reason=AIGenerationFailureReason.PROVIDER_TIMEOUT,
                ) from exc
            except httpx.HTTPError as exc:
                raise TransientProviderError(
                    "OpenAI no está disponible.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                ) from exc

            if response.status_code == 429:
                raise TransientProviderError(
                    "OpenAI devolvió 429 (rate limited).",
                    reason=AIGenerationFailureReason.PROVIDER_RATE_LIMITED,
                )
            if response.status_code >= 500:
                raise TransientProviderError(
                    f"OpenAI devolvió {response.status_code}.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                )
            if response.status_code >= 400:
                raise OpenAIResponseError(
                    f"OpenAI devolvió {response.status_code}: {response.text[:500]}"
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise TransientProviderError(
                    "La respuesta de OpenAI no es JSON válido.",
                    reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
                ) from exc

            return _response_from_body(body)
        finally:
            if owns_client:
                await client.aclose()


def _response_from_body(body: dict[str, Any]) -> LanguageModelResponse:
    text = _extract_output_text(body)
    if not text:
        raise TransientProviderError(
            "OpenAI no devolvió ningún bloque de texto en la respuesta.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )

    usage = body.get("usage") or {}
    return LanguageModelResponse(
        text=text,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )


def _extract_output_text(body: dict[str, Any]) -> str:
    """No es seguro asumir `output[0].content[0].text` — `output` puede
    incluir llamadas a herramientas o tokens de razonamiento antes del
    mensaje real (ver docs/guides/text citado en el docstring del módulo).
    Recorre `output` buscando el primer mensaje `role=assistant` con
    bloques `output_text`."""
    try:
        output_items = body["output"]
    except (KeyError, TypeError) as exc:
        raise TransientProviderError(
            f"Forma de respuesta de OpenAI inesperada (falta {exc}).",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        ) from exc

    for item in output_items:
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        parts = [
            block.get("text", "")
            for block in item.get("content", [])
            if block.get("type") == "output_text"
        ]
        text = "".join(parts)
        if text:
            return text
    return ""
