"""MockSessionNotesGenerator: checklist basado en keywords, sin IA real.

Regla de seguridad clínica (docs/clinical-safety.md §6, misma que
`MockAnamnesisGenerator`): nunca rellena `text` sin una cita literal de
la transcripción ACTUAL que lo respalde — `previous_anamnesis_context` se
recibe (RFC técnico §8) pero nunca se usa como fuente de `source_excerpt`,
solo `MockLanguageModelProvider.complete()` lo ve, igual que
`MockAnamnesisGenerator` con `missing_information`. Bloque sin
coincidencia queda `text=""`/`source_excerpt=None` — nunca texto de
continuidad por cortesía (RFC §4.7).
"""

from __future__ import annotations

from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.session_notes_generator import (
    SESSION_NOTES_BLOCKS,
    SessionNotesBlock,
    SessionNotesDraft,
)
from app.integrations.mocks.mock_language_model_provider import MockLanguageModelProvider

_SYSTEM_PROMPT = (
    "Completa las notas de sesión estructuradas exclusivamente a partir "
    "de la transcripción actual. El contexto de anamnesis previa ayuda a "
    "interpretar referencias, pero nunca es evidencia de la sesión "
    "actual. Un bloque sin contenido queda con texto vacío — nunca "
    "rellenes por cortesía."
)

#: Caracteres de contexto a cada lado del match — mismo valor que
#: `mock_anamnesis_generator._EXCERPT_PADDING`.
_EXCERPT_PADDING = 60

#: (bloque, keyword, texto fijo de demostración) — checklist determinista,
#: sin IA de por medio, un keyword por bloque.
_BLOCK_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "changes_since_last_visit",
        "ha mejorado",
        "El paciente refiere mejoría desde la última visita.",
    ),
    (
        "device_adjustments",
        "ajustamos el volumen",
        "Se ajustó el volumen del audífono durante la sesión.",
    ),
    (
        "patient_reported_issues",
        "sigue notando",
        "El paciente sigue notando molestias pendientes de revisar.",
    ),
    (
        "next_steps",
        "próxima revisión",
        "Se programa próxima revisión de seguimiento.",
    ),
)


def _excerpt_around(transcript: str, lowered: str, keyword: str) -> str:
    """Ventana real de contexto alrededor de `keyword` — mismo patrón que
    `mock_anamnesis_generator._excerpt_around`/
    `mock_clinical_flags_generator._build_excerpt`: nunca
    `transcript[:200]` decorativo."""
    start = lowered.find(keyword)
    end = start + len(keyword)
    window_start = max(0, start - _EXCERPT_PADDING)
    window_end = min(len(transcript), end + _EXCERPT_PADDING)
    return transcript[window_start:window_end]


def _extract_blocks(transcript: str) -> dict[str, SessionNotesBlock]:
    lowered = transcript.lower()
    blocks: dict[str, SessionNotesBlock] = {
        block_name: SessionNotesBlock(text="", source_excerpt=None)
        for block_name in SESSION_NOTES_BLOCKS
    }

    for block_name, keyword, fixed_text in _BLOCK_RULES:
        if keyword in lowered:
            blocks[block_name] = SessionNotesBlock(
                text=fixed_text,
                source_excerpt=_excerpt_around(transcript, lowered, keyword),
            )

    return blocks


class MockSessionNotesGenerator:
    def __init__(self, language_model_provider: LanguageModelProvider | None = None) -> None:
        self._llm = language_model_provider or MockLanguageModelProvider()

    async def generate(
        self,
        transcript: str,
        previous_anamnesis_context: str | None,
        *,
        context: SessionContext,
    ) -> SessionNotesDraft:
        await self._llm.complete(
            RenderedPrompt(
                system=_SYSTEM_PROMPT,
                user=(
                    f"Transcripción actual:\n{transcript}\n\n"
                    f"Contexto de anamnesis previa (solo para interpretar, "
                    f"nunca evidencia de esta sesión): "
                    f"{previous_anamnesis_context or '(sin contexto previo)'}"
                ),
            ),
            model="mock-v1",
        )
        return SessionNotesDraft(blocks=_extract_blocks(transcript))
