"""MockMissingInformationGenerator: compone MockLanguageModelProvider, salida determinista.

Target-aware (Fase 6.4.4, RFC técnico de 6.4 §6): el fixture devuelto
depende exclusivamente de `target`, nunca del contenido de `summary`/
`clinical_flags` — determinista y suficiente para demostrar que el
target se propaga correctamente, sin inventar lógica clínica de gap
real. `ANAMNESIS_FIELDS` evalúa gaps contra los 20 campos de anamnesis;
`SESSION_NOTES_BLOCKS` evalúa gaps contra los 4 bloques de notas de
sesión — nunca se reutilizan los campos de un target para el otro.
"""

from __future__ import annotations

from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.missing_information_generator import (
    MissingInfoItem,
    MissingInformationResult,
    MissingInformationTarget,
)
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "A partir del resumen y las señales detectadas, sugiere preguntas de "
    "seguimiento sobre información que convendría ampliar respecto al "
    "esquema objetivo indicado. Nunca afirmes que algo ocurrió si no hay "
    "evidencia."
)

#: Fixture determinista para target=ANAMNESIS_FIELDS: coherente con la
#: transcripción de MockTranscriptionProvider (que explícitamente no
#: aborda antecedentes familiares ni exposición a ruido) — ambos topics
#: son campos reales de `ANAMNESIS_FIELDS`.
_ANAMNESIS_FIELDS_ITEMS: tuple[MissingInfoItem, ...] = (
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

#: Fixture determinista para target=SESSION_NOTES_BLOCKS: ambos topics
#: son bloques reales de `SESSION_NOTES_BLOCKS` — nunca campos de
#: ANAMNESIS_FIELDS.
_SESSION_NOTES_BLOCKS_ITEMS: tuple[MissingInfoItem, ...] = (
    MissingInfoItem(
        topic="device_adjustments",
        suggested_question="¿Se ha realizado algún ajuste en el audífono desde la última visita?",
    ),
    MissingInfoItem(
        topic="next_steps",
        suggested_question="¿Se ha acordado la próxima revisión de seguimiento?",
    ),
)

_ITEMS_BY_TARGET: dict[MissingInformationTarget, tuple[MissingInfoItem, ...]] = {
    MissingInformationTarget.ANAMNESIS_FIELDS: _ANAMNESIS_FIELDS_ITEMS,
    MissingInformationTarget.SESSION_NOTES_BLOCKS: _SESSION_NOTES_BLOCKS_ITEMS,
}


class MockMissingInformationGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(
        self,
        summary: str,
        clinical_flags: list[ClinicalFlagDraft],
        *,
        target: MissingInformationTarget,
        context: SessionContext,
    ) -> MissingInformationResult:
        await self._llm.complete(
            RenderedPrompt(
                system=_SYSTEM_PROMPT,
                user=(
                    f"Esquema objetivo: {target.value}\n"
                    f"Resumen:\n{summary}\n\nSeñales detectadas: {len(clinical_flags)}"
                ),
            ),
            model="mock-v1",
        )
        return MissingInformationResult(items=list(_ITEMS_BY_TARGET[target]))
