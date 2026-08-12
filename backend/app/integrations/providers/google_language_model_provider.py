"""GoogleLanguageModelProvider: proveedor LLM directo real (Fase 6.3.5).

Verificado contra la documentación pública oficial vigente el 2026-08-12
(no de memoria, no por lo observado en OpenRouter — encargo Fase 6.3,
decisión #2). Google reemplazó la antigua API `generateContent` por la
**Interactions API**, la recomendada actualmente para todos los modelos:

- Endpoint, headers y forma de request/response:
  https://ai.google.dev/gemini-api/docs/quickstart
  https://ai.google.dev/gemini-api/docs/text-generation
  https://ai.google.dev/gemini-api/docs/gemini-3
- Salida estructurada vía `response_format` (`type: "text"`,
  `mime_type: "application/json"`, `schema`) — confirmado por dos fuentes
  independientes: https://ai.google.dev/gemini-api/docs/structured-output
  y el resumen de docs.cloud.google.com/gemini-enterprise-agent-platform
  (encargo Fase 6.3.5: "utiliza structured JSON/schema si el modelo/API lo
  soporta realmente", nunca supuesto).
- Texto de salida en `output_text` a nivel superior de la respuesta:
  https://ai.google.dev/gemini-api/docs/structured-output
- Modelo `gemini-3.6-flash` confirmado como id nativo exacto (misma
  cadena que el benchmark de OpenRouter, sin el prefijo `google/`):
  https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash

**Único dato no confirmado por la documentación pública consultada**: el
nombre exacto de los campos de `usage` en la respuesta de la Interactions
API (ninguna de las páginas fetched mostró un ejemplo completo). Se
prueban varios candidatos plausibles y se usa el primero presente — nunca
se inventa un valor si ninguno existe (mismo criterio ya establecido en
`AssemblyAITranscriptionProvider._MODEL_FIELD_CANDIDATES`, Fase 5). Si
ninguno coincide, `input_tokens`/`output_tokens` quedan en `None` y
`run_provider_step` cae al `TokenCounter` heurístico — nunca un valor
inventado.

Ninguna llamada real se ha hecho contra esta API durante su
implementación. Usa `httpx` genérico, sin el SDK oficial de Google — mismo
criterio que el resto de proveedores directos de este módulo.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt

_INTERACTIONS_PATH = "/v1beta/interactions"

#: Candidatos plausibles para el recuento de tokens de entrada/salida en
#: la respuesta — no confirmados con un ejemplo oficial completo, ver
#: docstring del módulo. `(clave_contenedora, clave_campo)`; `None` como
#: clave_contenedora indica un campo de nivel superior.
_INPUT_TOKEN_CANDIDATES: tuple[tuple[str | None, str], ...] = (
    ("usage", "input_tokens"),
    ("usage_metadata", "prompt_token_count"),
)
_OUTPUT_TOKEN_CANDIDATES: tuple[tuple[str | None, str], ...] = (
    ("usage", "output_tokens"),
    ("usage_metadata", "candidates_token_count"),
)


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
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY es obligatoria para usar GoogleLanguageModelProvider.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._injected_client = http_client

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}

    def _payload(
        self, prompt: RenderedPrompt, model: str, response_json_schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "input": prompt.user}
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
    text = body.get("output_text")
    if not isinstance(text, str) or not text:
        raise TransientProviderError(
            "Google no devolvió 'output_text' en la respuesta.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )

    return LanguageModelResponse(
        text=text,
        input_tokens=_first_present(body, _INPUT_TOKEN_CANDIDATES),
        output_tokens=_first_present(body, _OUTPUT_TOKEN_CANDIDATES),
    )


def _first_present(
    body: dict[str, Any], candidates: tuple[tuple[str | None, str], ...]
) -> int | None:
    for container_key, field_key in candidates:
        container = body.get(container_key) if container_key else body
        if isinstance(container, dict) and isinstance(container.get(field_key), int):
            return container[field_key]
    return None
