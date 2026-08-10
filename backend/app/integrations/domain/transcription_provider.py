"""Puerto TranscriptionProvider.

Ver docs/ai-pipeline-architecture.md §6.1 y docs/transcription-benchmark.md
(Fase 5). `TranscriptionInput` es deliberadamente opaco respecto a si el
origen es audio real o una fixture de desarrollo: el paso del pipeline no
necesita saberlo, y sustituir el `Mock*` por un proveedor real no requiere
cambiar esta interfaz — ver docs/ai-pipeline-architecture.md §13 (pregunta
3, resuelta).

`AudioForTranscription` (Fase 5) es opcional: `MockTranscriptionProvider`
la ignora por completo (sigue devolviendo su fixture determinista, sin
`duration_ms` ni `segments`), preservando exactamente el comportamiento y
el `content` (`{"text", "language"}`) del Mock Pipeline existente. Solo un
proveedor que recibe `audio` (p. ej. `AssemblyAITranscriptionProvider`)
puede poblar `duration_ms`/`segments` en el resultado — nunca al revés.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class AudioForTranscription:
    """Audio real a transcribir — bytes ya leídos desde `AudioStorage`.

    El `TranscriptionProvider` nunca conoce `AudioStorage` ni
    `storage_reference`: solo recibe los bytes ya resueltos, para que la
    interfaz siga siendo agnóstica de dónde vive el fichero (ver
    docs/architecture.md §4)."""

    audio_bytes: bytes
    mime_type: str
    filename: str


@dataclass(slots=True, frozen=True)
class TranscriptionSegment:
    """Un fragmento diarizado del resultado normalizado — ver
    docs/transcription-benchmark.md §Contrato normalizado."""

    speaker: str | None
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True, frozen=True)
class TranscriptionInput:
    clinical_session_id: uuid.UUID
    audio: AudioForTranscription | None = None


@dataclass(slots=True, frozen=True)
class TranscriptionResult:
    text: str
    language: str
    confidence: int | None = None
    duration_ms: int | None = None
    segments: list[TranscriptionSegment] | None = None


class TranscriptionProvider(Protocol):
    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult: ...
