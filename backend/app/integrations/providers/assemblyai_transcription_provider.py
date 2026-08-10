"""AssemblyAITranscriptionProvider: primer proveedor real de transcripción.

Usa exclusivamente la API REST oficial de AssemblyAI (v2) vía `httpx` — un
cliente HTTP genérico, no un SDK de terceros (ver docs/transcription-benchmark.md
§AssemblyAI). Flujo: `POST /v2/upload` (sube los bytes) → `POST
/v2/transcript` (encola el job) → `GET /v2/transcript/{id}` (poll hasta
`completed`/`error`). La API key nunca se registra en logs ni se incluye
en ninguna excepción — solo viaja en la cabecera `authorization`.

**Fase 5.2 — perfiles baseline/optimized.** Todos los parámetros nuevos
(`speech_models`, `speakers_expected`, `medical_mode`, `keyterms_prompt`)
son opcionales con default `None`/`False`: una instancia construida como
antes (solo `api_key`/`language_code`/...) envía exactamente el mismo
cuerpo de petición que la Fase 5 — la reproducibilidad del perfil
baseline está garantizada a nivel de payload HTTP, no solo "misma clase".
Nombres de parámetro verificados contra la documentación oficial vigente
de AssemblyAI (docs/transcription-benchmark.md §Inspección de la API),
nunca supuestos.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.integrations.domain.transcription_provider import (
    TranscriptionInput,
    TranscriptionResult,
    TranscriptionSegment,
)

_UPLOAD_PATH = "/v2/upload"
_TRANSCRIPT_PATH = "/v2/transcript"
_TERMINAL_STATUSES = frozenset({"completed", "error"})
_MEDICAL_MODE_DOMAIN = "medical-v1"


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
        # --- Perfil experimental (Fase 5.2) — todos opcionales, sin efecto
        # sobre el payload si no se pasan (baseline reproducible). ---
        speech_models: list[str] | None = None,
        speakers_expected: int | None = None,
        medical_mode: bool = False,
        keyterms_prompt: list[str] | None = None,
        keyterm_set_version: str | None = None,
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
        self._speech_models = speech_models
        self._speakers_expected = speakers_expected
        self._medical_mode = medical_mode
        self._keyterms_prompt = keyterms_prompt
        self._keyterm_set_version = keyterm_set_version

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
            transcript,
            default_language=self._language_code,
            requested_language=self._language_code,
            speech_models_requested=self._speech_models,
            speakers_expected_requested=self._speakers_expected,
            medical_mode=self._medical_mode,
            keyterm_prompting=bool(self._keyterms_prompt),
            keyterm_set_version=self._keyterm_set_version,
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
        body: dict[str, Any] = {
            "audio_url": audio_url,
            "language_code": self._language_code,
            "speaker_labels": True,
        }
        # Cada parámetro solo se añade al cuerpo si se configuró
        # explícitamente — un perfil baseline (todos en None/False) envía
        # exactamente el mismo payload que la Fase 5.
        if self._speech_models:
            body["speech_models"] = self._speech_models
        if self._speakers_expected is not None:
            body["speakers_expected"] = self._speakers_expected
        if self._medical_mode:
            body["domain"] = _MEDICAL_MODE_DOMAIN
        if self._keyterms_prompt:
            body["keyterms_prompt"] = self._keyterms_prompt

        response = await client.post(_TRANSCRIPT_PATH, headers=self._headers(), json=body)
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
#: el primero presente — nunca se inventa un valor si ninguno existe. La
#: documentación oficial consultada (Fase 5.2) no confirma con certeza el
#: nombre exacto del campo de RESPUESTA que confirma el modelo
#: efectivamente usado (el parámetro de PETICIÓN es `speech_models`,
#: plural) — se comprueban varios candidatos plausibles, nunca se asume.
_MODEL_FIELD_CANDIDATES = ("speech_model", "language_model", "acoustic_model")


def _segment_from_word_group(speaker: str, words: list[dict]) -> TranscriptionSegment:
    return TranscriptionSegment(
        speaker=speaker,
        start_ms=words[0]["start"],
        end_ms=words[-1]["end"],
        text=" ".join(word["text"] for word in words),
    )


def _segments_from_words(words: list[dict]) -> list[TranscriptionSegment] | None:
    """Fallback (prioridad 3, ver docs/transcription-benchmark.md
    §Word timestamps/utterances): agrupa palabras consecutivas del mismo
    hablante en segmentos sintéticos cuando `utterances` no está
    disponible pero `words[].speaker` sí lo está — nunca colapsa la
    transcripción en un único segmento si hay granularidad de hablante
    disponible en otra forma."""
    words_with_speaker = [word for word in words if word.get("speaker")]
    if not words_with_speaker:
        return None

    segments: list[TranscriptionSegment] = []
    current_speaker = words_with_speaker[0]["speaker"]
    current_group: list[dict] = []
    for word in words_with_speaker:
        if word["speaker"] != current_speaker:
            segments.append(_segment_from_word_group(current_speaker, current_group))
            current_speaker = word["speaker"]
            current_group = []
        current_group.append(word)
    if current_group:
        segments.append(_segment_from_word_group(current_speaker, current_group))
    return segments or None


def _segments_from_transcript(transcript: dict) -> list[TranscriptionSegment] | None:
    """Prioridad de normalización (docs/transcription-benchmark.md
    §Word timestamps/utterances): 1) `utterances` con speaker (la
    estructura ya agrupada por turno que devuelve la API cuando
    `speaker_labels=True`); 2) `words` agrupadas por speaker si
    `utterances` no está disponible; 3) sin segmentos (comportamiento
    previo, artefacto sin diarización)."""
    utterances = transcript.get("utterances") or []
    if utterances:
        return [
            TranscriptionSegment(
                speaker=utterance.get("speaker"),
                start_ms=utterance["start"],
                end_ms=utterance["end"],
                text=utterance["text"],
            )
            for utterance in utterances
        ]

    words = transcript.get("words") or []
    return _segments_from_words(words)


def _normalize(
    transcript: dict,
    *,
    default_language: str,
    requested_language: str,
    speech_models_requested: list[str] | None,
    speakers_expected_requested: int | None,
    medical_mode: bool,
    keyterm_prompting: bool,
    keyterm_set_version: str | None,
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
    segments = _segments_from_transcript(transcript)

    model_name = next(
        (transcript[field] for field in _MODEL_FIELD_CANDIDATES if transcript.get(field)), None
    )
    # Metadata segura y ya extraída — nunca el `raw_response` completo
    # (ver docs/transcription-benchmark.md §Model traceability): qué se
    # pidió realmente frente a lo que el proveedor confirma haber hecho.
    # También alimenta el cálculo de coste por componentes (§Pricing).
    provider_metadata: dict[str, Any] = {
        "transcript_id": transcript.get("id"),
        "speaker_labels_requested": True,
        "diarization_used": bool(segments),
        "language_code_requested": requested_language,
        "language_code_detected": transcript.get("language_code"),
        "punctuate": transcript.get("punctuate"),
        "speech_models_requested": speech_models_requested,
        "speakers_expected_requested": speakers_expected_requested,
        "medical_mode": medical_mode,
        "keyterm_prompting": keyterm_prompting,
        "keyterm_set_version": keyterm_set_version,
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
