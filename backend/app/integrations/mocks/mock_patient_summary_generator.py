"""MockPatientSummaryGenerator: compone MockLanguageModelProvider, salida determinista."""

from __future__ import annotations

from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.patient_summary_generator import PatientSummaryDraft
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "Redacta una explicación breve, en lenguaje llano y sin jerga técnica, de la "
    "consulta para el propio paciente. Nunca presentes una inferencia como hecho "
    "clínico confirmado."
)


class MockPatientSummaryGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(
        self, transcript: str, summary_text: str, *, context: SessionContext
    ) -> PatientSummaryDraft:
        # La llamada demuestra la composición documentada
        # (docs/ai-pipeline-architecture.md §7.2); el mock no depende de su
        # respuesta para construir un texto legible.
        await self._llm.complete(
            RenderedPrompt(
                system=_SYSTEM_PROMPT,
                user=f"Transcripción:\n{transcript}\n\nResumen técnico:\n{summary_text}",
            ),
            model="mock-v1",
        )
        text = (
            "Explicación generada automáticamente (ficticia, sin IA real): durante la "
            "consulta se revisaron tus respuestas sobre la audición y se registraron "
            "algunos puntos que conviene comentar con tu profesional en la próxima cita. "
            "Contenido generado mediante IA simulada; pendiente de revisión profesional."
        )
        return PatientSummaryDraft(text=text)
