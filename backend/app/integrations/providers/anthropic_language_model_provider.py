"""AnthropicLanguageModelProvider: primer proveedor LLM directo real (Fase
6.3.5, RFC §6.1: "producción implementa LanguageModelProvider directamente
contra el proveedor/modelo ganador").

Verificado contra la documentación pública oficial vigente el 2026-08-12
(no de memoria, no por lo observado en OpenRouter — encargo Fase 6.3,
decisión #2):

- Endpoint, headers y forma de request/response del Messages API:
  https://platform.claude.com/docs/en/api/messages/create
  https://platform.claude.com/docs/en/get-started
  https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- Salida estructurada (`output_config.format`) y que `claude-opus-5` la
  soporta: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Modelo `claude-opus-5` confirmado como id nativo exacto (misma cadena
  que el benchmark de OpenRouter, sin el prefijo `anthropic/`) en la
  tarjeta de modelo de https://platform.claude.com/docs/en/home.

Ninguna llamada real se ha hecho contra esta API durante su implementación
(encargo Fase 6.3: "cero llamadas reales salvo autorización explícita
posterior"). Usa `httpx` genérico, sin el SDK oficial de Anthropic — mismo
criterio que `AssemblyAITranscriptionProvider`/`DeepgramTranscriptionProvider`
(Fase 5): API REST oficial documentada, sin dependencia de terceros nueva.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt

_MESSAGES_PATH = "/v1/messages"
#: Versión de API fijada por la documentación oficial (no cambia con cada
#: modelo) — ver quickstart citado en el docstring del módulo.
_ANTHROPIC_VERSION = "2023-06-01"
#: `max_tokens` es obligatorio en el Messages API (a diferencia de
#: OpenAI/Google). Corrección Fase 6.3 (auditoría 2026-08-13, "peor caso
#: del preflight vs techo real enviado al provider"): en producción,
#: `factory.py::build_language_model_provider` SIEMPRE pasa
#: `max_tokens=settings.llm_max_output_tokens_estimate` explícitamente —
#: la MISMA fuente de verdad que usa `run_provider_step` para el preflight
#: de coste (`context.max_output_tokens_estimate`, derivado del mismo
#: campo de `Settings`). Este valor (2000) solo se usa como fallback
#: cuando el provider se construye directamente sin pasar por la factory
#: (scripts de diagnóstico, tests) — nunca diverge del preflight en el
#: camino de producción real, a diferencia del `4096` independiente que
#: tenía antes este módulo (bug de cost-safety: el preflight asumía un
#: techo de 2000 mientras el provider podía pedir hasta 4096 tokens
#: reales — más del doble de coste no cubierto por el guardarraíl).
_DEFAULT_MAX_TOKENS = 2000


class AnthropicResponseError(Exception):
    """Error HTTP 4xx (salvo 429) — nunca retryable automáticamente
    (encargo Fase 6.3.5: "otros 4xx no se convierten en retryable
    automáticamente"). `_attempt()` en steps/base.py la captura como
    `unexpected_internal_error`, sin reintento. Nunca incluye cabeceras
    (donde viajaría la API key)."""


class AnthropicLanguageModelProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.anthropic.com",
        timeout_seconds: float = 120.0,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY es obligatoria para usar AnthropicLanguageModelProvider."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._injected_client = http_client

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _payload(
        self, prompt: RenderedPrompt, model: str, response_json_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt.user}],
        }
        if prompt.system is not None:
            payload["system"] = prompt.system
        if response_json_schema is not None:
            payload["output_config"] = {
                "format": {"type": "json_schema", "schema": response_json_schema}
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
            raise ValueError("AnthropicLanguageModelProvider.complete() requiere 'model'.")

        client = self._injected_client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        )
        owns_client = self._injected_client is None
        try:
            try:
                response = await client.post(
                    _MESSAGES_PATH,
                    headers=self._headers(),
                    json=self._payload(prompt, model, response_json_schema),
                )
            except httpx.TimeoutException as exc:
                raise TransientProviderError(
                    "Timeout esperando respuesta de Anthropic.",
                    reason=AIGenerationFailureReason.PROVIDER_TIMEOUT,
                ) from exc
            except httpx.HTTPError as exc:
                raise TransientProviderError(
                    "Anthropic no está disponible.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                ) from exc

            if response.status_code == 429:
                raise TransientProviderError(
                    "Anthropic devolvió 429 (rate limited).",
                    reason=AIGenerationFailureReason.PROVIDER_RATE_LIMITED,
                )
            if response.status_code >= 500:
                raise TransientProviderError(
                    f"Anthropic devolvió {response.status_code}.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                )
            if response.status_code >= 400:
                raise AnthropicResponseError(
                    f"Anthropic devolvió {response.status_code}: {response.text[:500]}"
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise TransientProviderError(
                    "La respuesta de Anthropic no es JSON válido.",
                    reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
                ) from exc

            return _response_from_body(body)
        finally:
            if owns_client:
                await client.aclose()


def _response_from_body(body: dict[str, Any]) -> LanguageModelResponse:
    try:
        content_blocks = body["content"]
        text = "".join(block["text"] for block in content_blocks if block.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise TransientProviderError(
            f"Forma de respuesta de Anthropic inesperada (falta {exc}).",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        ) from exc

    if not text:
        raise TransientProviderError(
            "Anthropic no devolvió ningún bloque de texto en la respuesta.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )

    usage = body.get("usage") or {}
    return LanguageModelResponse(
        text=text,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
