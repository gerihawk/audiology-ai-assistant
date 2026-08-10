"""Puerto TranscriptionProvider.

Ver docs/ai-pipeline-architecture.md §6.1. `TranscriptionInput` es
deliberadamente opaco respecto a si el origen es audio real o una fixture
de desarrollo: el paso del pipeline no necesita saberlo, y sustituir el
`Mock*` por un proveedor real (Whisper u otro) el día que exista audio no
requiere cambiar esta interfaz — ver docs/ai-pipeline-architecture.md §13
(pregunta 3, resuelta: el pipeline no depende de que exista audio real).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class TranscriptionInput:
    clinical_session_id: uuid.UUID


@dataclass(slots=True, frozen=True)
class TranscriptionResult:
    text: str
    language: str
    confidence: int | None = None


class TranscriptionProvider(Protocol):
    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult: ...
