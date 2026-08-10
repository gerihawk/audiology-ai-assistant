"""MockSummaryGenerator: compone MockLanguageModelProvider, salida determinista."""

from __future__ import annotations

from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.summary_generator import SummaryDraft
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "Genera un resumen profesional breve de la consulta, en lenguaje no "
    "diagnóstico. Nunca presentes una inferencia como hecho clínico "
    "confirmado."
)


class MockSummaryGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(self, transcript: str, *, context: SessionContext) -> SummaryDraft:
        # La llamada a `LanguageModelProvider` demuestra la composición
        # documentada (docs/ai-pipeline-architecture.md §7.2); el mock no
        # depende de su respuesta para construir un texto legible, ya que
        # `MockLanguageModelProvider` no interpreta contenido real.
        await self._llm.complete(
            RenderedPrompt(system=_SYSTEM_PROMPT, user=f"Transcripción:\n{transcript}"),
            model="mock-v1",
        )
        sentence_count = len([s for s in transcript.split(".") if s.strip()])
        text = (
            "Resumen generado automáticamente (ficticio, sin IA real): la consulta registró "
            f"{sentence_count} observaciones relevantes, incluida la exploración de acúfenos y "
            "la valoración de posibles síntomas de vértigo. Contenido generado mediante IA "
            "simulada; pendiente de revisión profesional."
        )
        return SummaryDraft(text=text)
