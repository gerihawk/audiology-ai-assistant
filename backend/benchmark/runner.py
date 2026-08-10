"""BenchmarkRunner: ejecuta el mismo caso del dataset contra varios
`TranscriptionProvider`.

Provider A / Provider B / Provider C -> Normalización -> Comparación ->
Informe (ver docs/transcription-benchmark.md). La "normalización" ya la
resuelve el propio contrato `TranscriptionResult` (todos los proveedores
devuelven la misma forma); este módulo no reinterpreta nada específico de
un proveedor concreto.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings
from app.integrations.domain.transcription_provider import (
    AudioForTranscription,
    TranscriptionInput,
    TranscriptionResult,
)
from app.integrations.factory import build_transcription_provider
from benchmark.dataset import DatasetCase

_MIME_TYPES_BY_EXTENSION: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
}


@dataclass(slots=True, frozen=True)
class BenchmarkOutcome:
    provider: str
    audio_id: str
    ran_at: str
    response_time_ms: int
    result: TranscriptionResult | None
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.result is not None


def _mime_type_for(extension: str) -> str:
    return _MIME_TYPES_BY_EXTENSION.get(extension.lower().lstrip("."), "application/octet-stream")


class BenchmarkRunner:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def run_one(self, provider_name: str, case: DatasetCase) -> BenchmarkOutcome:
        ran_at = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        try:
            provider = build_transcription_provider(self._settings, provider_name)
            audio_bytes = case.audio_path.read_bytes()
            transcription_input = TranscriptionInput(
                # El benchmark no tiene una sesión clínica real: valor
                # opaco exigido por el contrato, nunca persistido ni usado
                # por ningún TranscriptionProvider para nada más que
                # trazas de log opcionales.
                clinical_session_id=uuid.uuid4(),
                audio=AudioForTranscription(
                    audio_bytes=audio_bytes,
                    mime_type=_mime_type_for(case.audio_path.suffix),
                    filename=case.audio_path.name,
                ),
            )
            result = await provider.transcribe(transcription_input)
        except Exception as exc:  # noqa: BLE001 — un proveedor que falla no aborta el benchmark
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return BenchmarkOutcome(
                provider=provider_name,
                audio_id=case.id,
                ran_at=ran_at,
                response_time_ms=elapsed_ms,
                result=None,
                error=str(exc) or exc.__class__.__name__,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return BenchmarkOutcome(
            provider=provider_name,
            audio_id=case.id,
            ran_at=ran_at,
            response_time_ms=elapsed_ms,
            result=result,
            error=None,
        )

    async def run_many(
        self, provider_names: list[str], case: DatasetCase
    ) -> list[BenchmarkOutcome]:
        return [await self.run_one(name, case) for name in provider_names]
