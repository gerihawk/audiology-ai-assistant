"""MockTranscriptionProvider: transcripción fija de fixture, sin IA real.

Devuelve siempre el mismo texto determinista, independientemente de la
sesión — no hay audio real todavía (ver
docs/ai-pipeline-architecture.md §13, pregunta 3, resuelta). El texto
incluye menciones reconocibles (acúfenos, negación de vértigo) para que
los demás mocks puedan demostrar de forma determinista la regla de "nunca
`informado` sin evidencia" (ver docs/clinical-safety.md §6).
"""

from __future__ import annotations

from app.integrations.domain.transcription_provider import TranscriptionInput, TranscriptionResult

FIXTURE_TRANSCRIPT_TEXT = (
    "El paciente refiere acúfenos en el oído izquierdo desde hace "
    "aproximadamente tres meses, de intensidad leve y carácter continuo. "
    "Niega vértigo o sensación de inestabilidad. No se ha preguntado por "
    "antecedentes familiares de pérdida auditiva ni por exposición "
    "laboral a ruido."
)

_MOCK_CONFIDENCE = 70


class MockTranscriptionProvider:
    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult:
        return TranscriptionResult(
            text=FIXTURE_TRANSCRIPT_TEXT, language="es", confidence=_MOCK_CONFIDENCE
        )
