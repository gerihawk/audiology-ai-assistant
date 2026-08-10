"""DeepgramTranscriptionProvider: segundo proveedor real de transcripción
(Fase 5.3) — ver docs/transcription-benchmark.md §Deepgram.

Usa exclusivamente la API REST oficial de Deepgram (`/v1/listen`) vía
`httpx` — sin SDK de terceros. A diferencia de AssemblyAI, **una única
petición síncrona**: el audio se envía como cuerpo binario directamente
(sin paso previo de subida) y la respuesta ya contiene la transcripción
completa — sin `polling` (parámetros verificados contra
developers.deepgram.com, nunca supuestos, ver docs/transcription-benchmark.md
§Investigación previa Deepgram). La API key nunca se registra en logs ni
se incluye en ninguna excepción — solo viaja en la cabecera
`authorization`.

Nota de normalización importante: `start`/`end` en `utterances`/`words`
de Deepgram vienen en **segundos** (Deepgram), frente a **milisegundos**
en AssemblyAI — cada proveedor convierte a `start_ms`/`end_ms` según su
propia unidad nativa; el contrato normalizado (`TranscriptionSegment`)
siempre expone milisegundos, el resto del sistema nunca ve segundos.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.integrations.domain.transcription_provider import (
    TranscriptionInput,
    TranscriptionResult,
    TranscriptionSegment,
)

_LISTEN_PATH = "/v1/listen"


class DeepgramTranscriptionProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.eu.deepgram.com",
        language_code: str = "es",
        model: str = "nova-3",
        timeout_seconds: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
        keyterms: list[str] | None = None,
        keyterm_set_version: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "DEEPGRAM_API_KEY es obligatoria para usar DeepgramTranscriptionProvider "
                "(TRANSCRIPTION_PROVIDER=deepgram)."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._language_code = language_code
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._injected_client = http_client
        self._keyterms = keyterms
        self._keyterm_set_version = keyterm_set_version

    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult:
        if input.audio is None:
            raise ValueError(
                "DeepgramTranscriptionProvider requiere audio real "
                "(TranscriptionInput.audio) — no hay fixture para este proveedor."
            )

        client = self._injected_client or httpx.AsyncClient(base_url=self._base_url)
        owns_client = self._injected_client is None
        try:
            # Síncrono, sin polling (a diferencia de AssemblyAI): una única
            # petición cuya respuesta ya contiene la transcripción
            # completa — el timeout cubre toda la duración del
            # procesamiento en el lado de Deepgram.
            response = await client.post(
                _LISTEN_PATH,
                headers=self._headers(input.audio.mime_type),
                params=self._params(),
                content=input.audio.audio_bytes,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        return _normalize(
            data,
            default_language=self._language_code,
            requested_language=self._language_code,
            base_url=self._base_url,
            keyterm_prompting=bool(self._keyterms),
            keyterm_set_version=self._keyterm_set_version,
        )

    def _headers(self, mime_type: str) -> dict[str, str]:
        # La API key nunca se registra: solo vive en esta cabecera, nunca
        # en un mensaje de excepción ni en un log.
        return {"authorization": f"Token {self._api_key}", "content-type": mime_type}

    def _params(self) -> list[tuple[str, str]]:
        params = [
            ("model", self._model),
            ("language", self._language_code),
            ("diarize", "true"),
            ("utterances", "true"),
            ("smart_format", "true"),
            ("punctuate", "true"),
        ]
        if self._keyterms:
            params.extend(("keyterm", term) for term in self._keyterms)
        return params


def _segment_from_word_group(speaker: int, words: list[dict]) -> TranscriptionSegment:
    return TranscriptionSegment(
        speaker=str(speaker),
        start_ms=int(words[0]["start"] * 1000),
        end_ms=int(words[-1]["end"] * 1000),
        text=" ".join(word.get("punctuated_word") or word["word"] for word in words),
    )


def _segments_from_words(words: list[dict]) -> list[TranscriptionSegment] | None:
    """Fallback (prioridad 2, ver docs/transcription-benchmark.md
    §Normalización de speakers): agrupa palabras consecutivas del mismo
    hablante cuando `utterances` no está disponible pero `words[].speaker`
    sí lo está."""
    words_with_speaker = [word for word in words if word.get("speaker") is not None]
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


def _first_alternative(data: dict) -> dict:
    channels = data.get("results", {}).get("channels") or []
    if not channels:
        return {}
    alternatives = channels[0].get("alternatives") or []
    return alternatives[0] if alternatives else {}


def _segments_from_transcript(data: dict) -> list[TranscriptionSegment] | None:
    """Prioridad de normalización (docs/transcription-benchmark.md
    §Normalización de speakers): 1) `results.utterances` con speaker (ya
    agrupadas por turno); 2) `words` del canal/alternativa principal
    agrupadas por speaker; 3) sin segmentos."""
    utterances = data.get("results", {}).get("utterances") or []
    if utterances:
        return [
            TranscriptionSegment(
                speaker=(
                    str(utterance["speaker"]) if utterance.get("speaker") is not None else None
                ),
                start_ms=int(utterance["start"] * 1000),
                end_ms=int(utterance["end"] * 1000),
                text=utterance.get("transcript", ""),
            )
            for utterance in utterances
        ]

    words = _first_alternative(data).get("words") or []
    return _segments_from_words(words)


def _normalize(
    data: dict,
    *,
    default_language: str,
    requested_language: str,
    base_url: str,
    keyterm_prompting: bool,
    keyterm_set_version: str | None,
) -> TranscriptionResult:
    alternative = _first_alternative(data)
    duration_seconds = data.get("metadata", {}).get("duration")
    duration_ms = int(duration_seconds * 1000) if duration_seconds is not None else None
    raw_confidence = alternative.get("confidence")
    confidence = round(raw_confidence * 100) if raw_confidence is not None else None
    segments = _segments_from_transcript(data)

    model_ids = data.get("metadata", {}).get("models") or []
    model_info_map = data.get("metadata", {}).get("model_info") or {}
    model_info: dict[str, Any] = model_info_map.get(model_ids[0], {}) if model_ids else {}
    model_name = model_info.get("name")
    model_version = model_info.get("version")

    provider_metadata: dict[str, Any] = {
        "request_id": data.get("metadata", {}).get("request_id"),
        "model_version": model_version,
        "model_arch": model_info.get("arch"),
        "diarization_requested": True,
        "diarization_used": bool(segments),
        "smart_format_requested": True,
        "language_code_requested": requested_language,
        "keyterm_prompting": keyterm_prompting,
        "keyterm_set_version": keyterm_set_version,
        "api_base": base_url,
        "region": "eu" if "eu.deepgram.com" in base_url else "us",
    }

    return TranscriptionResult(
        text=alternative.get("transcript") or "",
        language=requested_language or default_language,
        confidence=confidence,
        duration_ms=duration_ms,
        segments=segments,
        model_name=model_name,
        provider_metadata=provider_metadata,
    )
