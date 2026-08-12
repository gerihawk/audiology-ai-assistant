"""MockMissingInformationGenerator: compone MockLanguageModelProvider, salida determinista."""

from __future__ import annotations

from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.missing_information_generator import (
    MissingInfoItem,
    MissingInformationResult,
)
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "A partir del resumen y las señales detectadas, sugiere preguntas de "
    "seguimiento sobre información que convendría ampliar. Nunca afirmes "
    "que algo ocurrió si no hay evidencia."
)

#: Fixture determinista: siempre las mismas dos sugerencias, coherentes
#: con la transcripción de MockTranscriptionProvider (que explícitamente
#: no aborda antecedentes familiares ni exposición a ruido).
_FIXTURE_ITEMS: tuple[MissingInfoItem, ...] = (
    MissingInfoItem(
        topic="antecedentes_familiares",
        suggested_question="¿Existen antecedentes familiares de pérdida auditiva?",
    ),
    MissingInfoItem(
        topic="exposicion_ruido",
        suggested_question=(
            "¿Ha estado expuesto a ruido laboral o recreativo de forma prolongada?"
        ),
    ),
)


class MockMissingInformationGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(
        self,
        summary: str,
        clinical_flags: list[ClinicalFlagDraft],
        *,
        context: SessionContext,
    ) -> MissingInformationResult:
        await self._llm.complete(
            RenderedPrompt(
                system=_SYSTEM_PROMPT,
                user=f"Resumen:\n{summary}\n\nSeñales detectadas: {len(clinical_flags)}",
            ),
            model="mock-v1",
        )
        return MissingInformationResult(items=list(_FIXTURE_ITEMS))
