"""MockAnamnesisGenerator: compone MockLanguageModelProvider, salida determinista.

Regla de seguridad clínica (docs/clinical-safety.md §6): nunca asigna
`informado`/`negado_explicitamente` sin una cita literal de la
transcripción que lo respalde. Todo campo sin coincidencia queda en
`no_preguntado` — nunca se inventa un valor.

`source_excerpt` (Fase 6.4.2, RFC técnico §6): ventana real de la
transcripción alrededor de la keyword que disparó el campo — nunca
`transcript[:200]` decorativo ni el texto de `value` (que es una
paráfrasis, no una cita) — mismo patrón ya usado por
`mock_clinical_flags_generator.py`. Garantiza por construcción que
`GroundingValidator.verify_excerpt` encuentra el excerpt de forma
literal en el transcript.
"""

from __future__ import annotations

from app.integrations.domain.anamnesis_generator import (
    ANAMNESIS_FIELDS,
    AnamnesisDraft,
    AnamnesisFieldStatus,
    AnamnesisFieldValue,
)
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.missing_information_generator import MissingInfoItem
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "Completa la anamnesis estructurada exclusivamente a partir de la "
    "transcripción. Nunca asignes 'informado' o 'negado_explicitamente' "
    "sin una cita literal que lo respalde; en caso de duda, usa "
    "'no_determinado'. Si no se abordó, usa 'no_preguntado'."
)

#: Caracteres de contexto a cada lado del match — mismo valor que
#: `mock_clinical_flags_generator._EXCERPT_PADDING`.
_EXCERPT_PADDING = 60


def _excerpt_around(transcript: str, lowered: str, keyword: str) -> str:
    """Ventana real de contexto alrededor de `keyword` — ver docstring del
    módulo. `keyword` debe existir en `lowered` (el llamador ya lo
    comprobó); la posición se busca en minúsculas pero el recorte final
    se toma del transcript ORIGINAL, para que el excerpt siga siendo una
    cita literal y no una versión en minúsculas del texto real."""
    start = lowered.find(keyword)
    end = start + len(keyword)
    window_start = max(0, start - _EXCERPT_PADDING)
    window_end = min(len(transcript), end + _EXCERPT_PADDING)
    return transcript[window_start:window_end]


def _extract_fields(transcript: str) -> dict[str, AnamnesisFieldValue]:
    lowered = transcript.lower()
    fields: dict[str, AnamnesisFieldValue] = {
        name: AnamnesisFieldValue(
            value="", status=AnamnesisFieldStatus.NO_PREGUNTADO, source_excerpt=None
        )
        for name in ANAMNESIS_FIELDS
    }

    if "acúfenos" in lowered:
        fields["tinnitus"] = AnamnesisFieldValue(
            value="Acúfenos en oído izquierdo, aproximadamente 3 meses, intensidad leve.",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt=_excerpt_around(transcript, lowered, "acúfenos"),
        )

    if "niega vértigo" in lowered:
        fields["vertigo_o_inestabilidad"] = AnamnesisFieldValue(
            value="El paciente niega vértigo o sensación de inestabilidad.",
            status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
            source_excerpt=_excerpt_around(transcript, lowered, "niega vértigo"),
        )

    return fields


class MockAnamnesisGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(
        self,
        transcript: str,
        missing_information: list[MissingInfoItem],
        *,
        context: SessionContext,
    ) -> AnamnesisDraft:
        await self._llm.complete(
            RenderedPrompt(
                system=_SYSTEM_PROMPT,
                user=(
                    f"Transcripción:\n{transcript}\n\n"
                    f"Información ausente ya identificada: "
                    f"{', '.join(item.topic for item in missing_information)}"
                ),
            ),
            model="mock-v1",
        )
        return AnamnesisDraft(fields=_extract_fields(transcript))
