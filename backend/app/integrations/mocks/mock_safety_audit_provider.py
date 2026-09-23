"""MockSafetyAuditProvider: veredicto determinista, sin llamada de red.

Mismo patrón que `MockLanguageModelProvider` (implementa el mismo puerto
`LanguageModelProvider`), pero devuelve una respuesta con la FORMA que
`app/ai_pipeline/domain/safety_audit.py::parse_safety_audit_response`
espera (JSON con `flagged`/`reasoning`/`field`), no texto de generación de
contenido — el mock genérico no sirve aquí porque su salida no es un
veredicto parseable. `flagged=False` por defecto; los tests que necesiten
simular un hallazgo instancian con `flagged=True`."""

from __future__ import annotations

import json
from typing import Any

from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt


class MockSafetyAuditProvider:
    def __init__(
        self,
        *,
        flagged: bool = False,
        reasoning: str = "Mock: sin hallazgos.",
        field: str | None = None,
    ) -> None:
        self._flagged = flagged
        self._reasoning = reasoning
        self._field = field

    async def complete(
        self,
        prompt: RenderedPrompt,
        *,
        model: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> LanguageModelResponse:
        payload = {"flagged": self._flagged, "reasoning": self._reasoning, "field": self._field}
        return LanguageModelResponse(text=json.dumps(payload, ensure_ascii=False))
