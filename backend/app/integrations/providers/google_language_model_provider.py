"""GoogleLanguageModelProvider: proveedor LLM directo real (Fase 6.3.5,
corregido tras la primera llamada real diagnóstica autorizada el
2026-08-13 — ver informe de esa prueba).

Verificado contra la documentación pública oficial vigente y contra la
respuesta real observada en la única llamada diagnóstica autorizada hasta
ahora (prompt sintético, sin datos clínicos):

- Endpoint, headers y forma de request:
  https://ai.google.dev/gemini-api/docs/quickstart
  https://ai.google.dev/gemini-api/docs/text-generation
  https://ai.google.dev/gemini-api/docs/gemini-3
- Salida estructurada vía `response_format` — confirmado que la petición
  es aceptada (200) en la llamada real.
- Modelo `gemini-3.6-flash` confirmado como id nativo exacto — la propia
  respuesta real lo devuelve en `body["model"]`.

**Corrección del hito 6.3.5 (basada en documentación oficial +
respuesta real, sin nueva llamada)**:

1. `output_text` **no existe** en la respuesta REST cruda de la
   Interactions API — es una comodidad añadida por SDKs de cliente, nunca
   un campo del wire format (confirmado: la respuesta real no lo
   contenía). El texto generado vive dentro de `steps[]`, en el/los
   step(s) con `type == "model_output"`, cada uno con un array `content`
   de bloques; solo los bloques `type == "text"` son texto generado —
   ver `_extract_text_from_steps()`.
2. Los nombres reales de `usage` (confirmados por
   https://ai.google.dev/api/interactions-api, coincidentes exactamente
   con la respuesta real observada: 47+16+195=258) son
   `total_input_tokens`/`total_output_tokens`/`total_thought_tokens` —
   nunca `input_tokens`/`output_tokens` ni
   `usage_metadata.prompt_token_count`/`candidates_token_count` (los
   candidatos especulativos del hito 6.3.5 original, sin base
   documental confirmada — eliminados, no hay superficie oficial
   alternativa que los use en este contrato).
3. `total_thought_tokens` es un contador de tokens de razonamiento
   FACTURABLE (https://ai.google.dev/gemini-api/docs/pricing: "Output
   price (including thinking tokens)" — la tarifa de output se aplica
   también a estos tokens) pero SEPARADO y ADITIVO de
   `total_output_tokens` — la aritmética de la respuesta real
   (input + output + thought == total, exactamente) solo se sostiene si
   son contadores disjuntos. Se expone en
   `LanguageModelResponse.reasoning_tokens`, nunca sumado silenciosamente
   a `output_tokens` (ver ese dataclass para el porqué y quién hace la
   suma).

Ninguna llamada real adicional se ha hecho durante esta corrección — solo
documentación pública y la respuesta ya capturada en la llamada
diagnóstica autorizada. Usa `httpx` genérico, sin el SDK oficial de
Google — mismo criterio que el resto de proveedores directos de este
módulo.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt

_INTERACTIONS_PATH = "/v1beta/interactions"

_STEP_TYPE_MODEL_OUTPUT = "model_output"
_CONTENT_BLOCK_TYPE_TEXT = "text"

#: Corrección Fase 6.3 (auditoría 2026-08-13): antes de esta corrección,
#: este adapter nunca enviaba `generation_config.max_output_tokens` a la
#: Interactions API — el preflight de coste asumía un peor caso
#: (`llm_max_output_tokens_estimate`) que el provider no estaba obligado a
#: respetar. `factory.py::build_language_model_provider` SIEMPRE pasa
#: `max_output_tokens=settings.llm_max_output_tokens_estimate` — la misma
#: fuente de verdad que usa `run_provider_step` para el preflight. Este
#: valor (2000) es solo el fallback para construcción directa fuera de la
#: factory (scripts/tests). Nombre de campo (`generation_config.
#: max_output_tokens`) confirmado contra https://ai.google.dev/api/interactions-api.
_DEFAULT_MAX_OUTPUT_TOKENS = 2000


class GoogleResponseError(Exception):
    """Error HTTP 4xx (salvo 429) — nunca retryable automáticamente. Nunca
    incluye cabeceras (donde viajaría la API key)."""


class GoogleLanguageModelProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout_seconds: float = 120.0,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY es obligatoria para usar GoogleLanguageModelProvider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._injected_client = http_client

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}

    def _payload(
        self, prompt: RenderedPrompt, model: str, response_json_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input": prompt.user,
            "generation_config": {"max_output_tokens": self._max_output_tokens},
        }
        if prompt.system is not None:
            payload["system_instruction"] = prompt.system
        if response_json_schema is not None:
            payload["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": response_json_schema,
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
            raise ValueError("GoogleLanguageModelProvider.complete() requiere 'model'.")

        client = self._injected_client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        )
        owns_client = self._injected_client is None
        try:
            try:
                response = await client.post(
                    _INTERACTIONS_PATH,
                    headers=self._headers(),
                    json=self._payload(prompt, model, response_json_schema),
                )
            except httpx.TimeoutException as exc:
                raise TransientProviderError(
                    "Timeout esperando respuesta de Google.",
                    reason=AIGenerationFailureReason.PROVIDER_TIMEOUT,
                ) from exc
            except httpx.HTTPError as exc:
                raise TransientProviderError(
                    "Google no está disponible.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                ) from exc

            if response.status_code == 429:
                raise TransientProviderError(
                    "Google devolvió 429 (rate limited).",
                    reason=AIGenerationFailureReason.PROVIDER_RATE_LIMITED,
                )
            if response.status_code >= 500:
                raise TransientProviderError(
                    f"Google devolvió {response.status_code}.",
                    reason=AIGenerationFailureReason.PROVIDER_UNAVAILABLE,
                )
            if response.status_code >= 400:
                raise GoogleResponseError(
                    f"Google devolvió {response.status_code}: {response.text[:500]}"
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise TransientProviderError(
                    "La respuesta de Google no es JSON válido.",
                    reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
                ) from exc

            return _response_from_body(body)
        finally:
            if owns_client:
                await client.aclose()


def _response_from_body(body: dict[str, Any]) -> LanguageModelResponse:
    text = _extract_text_from_steps(body)
    usage = body.get("usage") or {}
    return LanguageModelResponse(
        text=text,
        input_tokens=_int_or_none(usage.get("total_input_tokens")),
        output_tokens=_int_or_none(usage.get("total_output_tokens")),
        reasoning_tokens=_int_or_none(usage.get("total_thought_tokens")),
    )


def _extract_text_from_steps(body: dict[str, Any]) -> str:
    """Recorre `body["steps"]` en orden; de cada step con
    `type == "model_output"`, concatena (sin separador) el `text` de cada
    bloque de su `content` con `type == "text"` — nunca bloques de otro
    tipo (imagen/audio/...), nunca otros tipos de step (llamadas a
    herramientas, resultados de herramientas, contenido de sistema) y
    nunca resúmenes de razonamiento («thought»), que Google no expone como
    contenido de texto normal en `content` (ver `usage.total_thought_tokens`
    para su recuento, nunca su contenido). Si hay varios steps
    `model_output`, sus textos se concatenan en el mismo orden — regla
    determinista única, documentada aquí, no en el llamador.

    Nunca busca JSON en texto libre ni intenta reparar markdown — un
    `model_output` ausente, sin bloques de texto, o una estructura
    `steps`/`content` inválida es siempre `INVALID_RESPONSE_FORMAT`."""
    steps = body.get("steps")
    if not isinstance(steps, list):
        raise TransientProviderError(
            "La respuesta de Google no incluye 'steps' (lista).",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )

    parts: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != _STEP_TYPE_MODEL_OUTPUT:
            continue
        content = step.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == _CONTENT_BLOCK_TYPE_TEXT
                and isinstance(block.get("text"), str)
            ):
                parts.append(block["text"])

    text = "".join(parts)
    if not text:
        raise TransientProviderError(
            "Google no devolvió ningún step 'model_output' con contenido de texto.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )
    return text


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
