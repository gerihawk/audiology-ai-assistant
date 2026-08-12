"""MockLanguageModelProvider: completado determinista, sin llamada de red.

No interpreta el prompt con ningún modelo real; construye una respuesta
fija y reproducible a partir del texto de usuario recibido. Sirve para
que los generators que la componen (`MockSummaryGenerator`,
`MockMissingInformationGenerator`, `MockAnamnesisGenerator`) queden ya
estructurados para sustituir esta única pieza por un proveedor real en el
futuro sin cambiar su propia lógica de parseo/validación — ver
docs/ai-pipeline-architecture.md §7.2.
"""

from __future__ import annotations

from typing import Any

from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt


class MockLanguageModelProvider:
    async def complete(
        self,
        prompt: RenderedPrompt,
        *,
        model: str | None = None,
        response_json_schema: dict[str, Any] | None = None,
    ) -> LanguageModelResponse:
        # `response_json_schema` (Fase 6.3.5) se ignora deliberadamente: el
        # mock no interpreta ningún schema, solo devuelve texto fijo.
        return LanguageModelResponse(text=f"[mock:{model or 'mock-v1'}] {prompt.user}")
