"""`BenchmarkLLMClient` — cliente HTTP hacia OpenRouter, EXCLUSIVO del
benchmark de generación (docs/fase-6-rfc.md §6.1: "OpenRouter se usa solo
en el benchmark... No recibe tráfico clínico de producción"). Nunca se
importa desde `app/`, nunca implementa `LanguageModelProvider`
productivo.

Mismo patrón que `AssemblyAITranscriptionProvider` (`httpx` genérico, sin
SDK de terceros; inyección opcional de `httpx.AsyncClient` para tests;
`owns_client`/`aclose()`) — ver
`app/integrations/providers/assemblyai_transcription_provider.py`.

**Verificación pendiente contra documentación oficial** (encargo Fase 6.2
§9/§25, antes de cualquier llamada real): la forma de request/response
implementada aquí sigue el contrato OpenAI-compatible que OpenRouter
documenta públicamente (`POST /chat/completions`, `Authorization: Bearer
<key>`, `usage.prompt_tokens`/`completion_tokens`) — los parámetros
exactos de structured output y el origen del coste autoritativo
(`usage.cost` vs. endpoint `/generation`) se confirman en el informe
previo a llamadas reales del hito 6.2, nunca se asumen aquí sin
verificar.

La API key nunca se registra en logs ni se incluye en ninguna excepción —
solo viaja en la cabecera `Authorization` de la petición saliente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_CHAT_COMPLETIONS_PATH = "/chat/completions"


class OpenRouterError(Exception):
    """Base de los errores del cliente — nunca incluye la API key."""


class OpenRouterAuthenticationError(OpenRouterError):
    """No hay `OPENROUTER_API_KEY` configurada — falla explícita, nunca
    una llamada anónima ni un fallback silencioso a otro proveedor."""


class OpenRouterTimeoutError(OpenRouterError):
    pass


class OpenRouterRateLimitError(OpenRouterError):
    pass


class OpenRouterProviderError(OpenRouterError):
    """Error HTTP 4xx/5xx distinto de rate limit — el cuerpo se incluye
    truncado (nunca cabeceras, que es donde viajaría la API key)."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"OpenRouter devolvió {status_code}: {body[:500]}")
        self.status_code = status_code


class OpenRouterMalformedResponseError(OpenRouterError):
    """La respuesta no es JSON válido, o no tiene la forma
    `choices[0].message.content` esperada."""


@dataclass(slots=True, frozen=True)
class LlmCompletionRequest:
    model: str
    system_prompt: str | None
    user_prompt: str
    #: Temperatura baja/0 para tareas estrictas (encargo §18) — nunca
    #: asume determinismo total de un proveedor cloud aunque sea 0.
    temperature: float = 0.0
    max_output_tokens: int | None = None
    #: JSON Schema para forzar structured output cuando el modelo lo
    #: soporta. Se envía si se aporta, pero la respuesta se valida
    #: igualmente con `validate_content_schema` en el runner — nunca se
    #: confía en que el proveedor cumplió el schema (encargo §14).
    response_json_schema: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class LlmCompletionResponse:
    raw_text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    #: Coste reportado por el propio proveedor si la respuesta lo incluye
    #: — `None` si no está disponible. Nunca se calcula aquí: el pricing
    #: local vive en `pricing.py`, nunca mezclado con este valor (encargo
    #: §16, "nunca mezclar provider reported cost con pricing table estimate").
    provider_reported_cost_usd: str | None


class BenchmarkLLMClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise OpenRouterAuthenticationError(
                "OPENROUTER_API_KEY es obligatoria para usar BenchmarkLLMClient "
                "(GENERATION_BENCHMARK_ENABLED=true)."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._injected_client = http_client

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _payload(self, request: LlmCompletionRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system_prompt is not None:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.response_json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "generation_output",
                    "strict": True,
                    "schema": request.response_json_schema,
                },
            }
        return payload

    async def complete(self, request: LlmCompletionRequest) -> LlmCompletionResponse:
        client = self._injected_client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        )
        owns_client = self._injected_client is None
        try:
            try:
                response = await client.post(
                    _CHAT_COMPLETIONS_PATH, headers=self._headers(), json=self._payload(request)
                )
            except httpx.TimeoutException as exc:
                raise OpenRouterTimeoutError("Timeout esperando respuesta de OpenRouter.") from exc

            if response.status_code == 429:
                raise OpenRouterRateLimitError("OpenRouter devolvió 429 (rate limited).")
            if response.status_code >= 400:
                raise OpenRouterProviderError(response.status_code, response.text)

            try:
                body = response.json()
            except ValueError as exc:
                raise OpenRouterMalformedResponseError("La respuesta no es JSON válido.") from exc

            return _response_from_body(body)
        finally:
            if owns_client:
                await client.aclose()


def _response_from_body(body: dict[str, Any]) -> LlmCompletionResponse:
    try:
        choice = body["choices"][0]
        raw_text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterMalformedResponseError(
            f"Forma de respuesta inesperada (falta {exc})."
        ) from exc

    if not isinstance(raw_text, str):
        raise OpenRouterMalformedResponseError("choices[0].message.content no es texto.")

    usage = body.get("usage") or {}
    return LlmCompletionResponse(
        raw_text=raw_text,
        model=body.get("model", ""),
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        provider_reported_cost_usd=str(usage["cost"]) if "cost" in usage else None,
    )
