"""AssemblyAITranscriptionProvider: primer proveedor real de transcripción.

Usa exclusivamente la API REST oficial de AssemblyAI (v2) vía `httpx` — un
cliente HTTP genérico, no un SDK de terceros (ver docs/transcription-benchmark.md
§AssemblyAI). Flujo: `POST /v2/upload` (sube los bytes) → `POST
/v2/transcript` (encola el job) → `GET /v2/transcript/{id}` (poll hasta
`completed`/`error`). La API key nunca se registra en logs ni se incluye
en ninguna excepción — solo viaja en la cabecera `authorization`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from app.integrations.domain.transcription_provider import (
    TranscriptionInput,
    TranscriptionResult,
    TranscriptionSegment,
)

_UPLOAD_PATH = "/v2/upload"
_TRANSCRIPT_PATH = "/v2/transcript"
_TERMINAL_STATUSES = frozenset({"completed", "error"})


class AssemblyAITranscriptionProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.assemblyai.com",
        language_code: str = "es",
        poll_interval_seconds: float = 2.0,
        poll_timeout_seconds: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY es obligatoria para usar AssemblyAITranscriptionProvider "
                "(TRANSCRIPTION_PROVIDER=assemblyai)."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._language_code = language_code
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_timeout_seconds = poll_timeout_seconds
        self._injected_client = http_client
        self._sleep = sleep

    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult:
        if input.audio is None:
            raise ValueError(
                "AssemblyAITranscriptionProvider requiere audio real "
                "(TranscriptionInput.audio) — no hay fixture para este proveedor."
            )

        client = self._injected_client or httpx.AsyncClient(base_url=self._base_url)
        owns_client = self._injected_client is None
        try:
            upload_url = await self._upload(client, input.audio.audio_bytes)
            transcript_id = await self._request_transcript(client, upload_url)
            transcript = await self._poll_until_terminal(client, transcript_id)
        finally:
            if owns_client:
                await client.aclose()

        return _normalize(
            transcript, default_language=self._language_code, requested_language=self._language_code
        )

    def _headers(self) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"authorization": self._api_key}

    async def _upload(self, client: httpx.AsyncClient, audio_bytes: bytes) -> str:
        response = await client.post(_UPLOAD_PATH, headers=self._headers(), content=audio_bytes)
        response.raise_for_status()
        return response.json()["upload_url"]

    async def _request_transcript(self, client: httpx.AsyncClient, audio_url: str) -> str:
        response = await client.post(
            _TRANSCRIPT_PATH,
            headers=self._headers(),
            json={
                "audio_url": audio_url,
                "language_code": self._language_code,
                "speaker_labels": True,
            },
        )
        response.raise_for_status()
        return response.json()["id"]

    async def _poll_until_terminal(self, client: httpx.AsyncClient, transcript_id: str) -> dict:
        elapsed = 0.0
        while True:
            response = await client.get(
                f"{_TRANSCRIPT_PATH}/{transcript_id}", headers=self._headers()
            )
            response.raise_for_status()
            transcript = response.json()
            if transcript.get("status") in _TERMINAL_STATUSES:
                return transcript

            if elapsed >= self._poll_timeout_seconds:
                raise TimeoutError(
                    f"AssemblyAI no completó la transcripción en "
                    f"{self._poll_timeout_seconds}s (transcript_id={transcript_id})."
                )
            await self._sleep(self._poll_interval_seconds)
            elapsed += self._poll_interval_seconds


#: Nombres de campo donde distintas versiones/planes de la API de
#: AssemblyAI han expuesto el modelo usado. Se prueban en orden y se usa
#: el primero presente — nunca se inventa un valor si ninguno existe.
_MODEL_FIELD_CANDIDATES = ("speech_model", "language_model", "acoustic_model")


def _normalize(
    transcript: dict, *, default_language: str, requested_language: str
) -> TranscriptionResult:
    if transcript.get("status") == "error":
        raise RuntimeError(f"AssemblyAI devolvió un error: {transcript.get('error')}")

    duration_ms = (
        int(transcript["audio_duration"] * 1000)
        if transcript.get("audio_duration") is not None
        else None
    )
    confidence = (
        round(transcript["confidence"] * 100) if transcript.get("confidence") is not None else None
    )
    utterances = transcript.get("utterances") or []
    segments = (
        [
            TranscriptionSegment(
                speaker=utterance.get("speaker"),
                start_ms=utterance["start"],
                end_ms=utterance["end"],
                text=utterance["text"],
            )
            for utterance in utterances
        ]
        if utterances
        else None
    )

    model_name = next(
        (transcript[field] for field in _MODEL_FIELD_CANDIDATES if transcript.get(field)), None
    )
    # Metadata segura y ya extraída — nunca el `raw_response` completo
    # (ver docs/transcription-benchmark.md §Model traceability): qué se
    # pidió realmente frente a lo que el proveedor confirma haber hecho.
    provider_metadata = {
        "transcript_id": transcript.get("id"),
        "speaker_labels_requested": True,
        "diarization_used": bool(segments),
        "language_code_requested": requested_language,
        "language_code_detected": transcript.get("language_code"),
        "punctuate": transcript.get("punctuate"),
    }

    return TranscriptionResult(
        text=transcript.get("text") or "",
        language=transcript.get("language_code") or default_language,
        confidence=confidence,
        duration_ms=duration_ms,
        segments=segments,
        model_name=model_name,
        provider_metadata=provider_metadata,
    )
