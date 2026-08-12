"""Parseo estricto de una respuesta cruda de `LanguageModelProvider` como
objeto JSON — compartido por los `Real*Generator` (Fase 6.3.6).

Nunca un parser heurístico (encargo Fase 6.3.6: "JSON inválido: usar
failure reason existente... No hagas parsing heurístico"): JSON inválido o
de forma inesperada (no es un objeto) siempre se traduce en
`TransientProviderError(INVALID_RESPONSE_FORMAT)` — nunca se intenta
extraer JSON de markdown fences ni de texto adicional alrededor.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError


def parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise TransientProviderError(
            "La respuesta del proveedor no es JSON válido.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        ) from exc
    if not isinstance(parsed, dict):
        raise TransientProviderError(
            "La respuesta del proveedor no es un objeto JSON.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )
    return parsed
