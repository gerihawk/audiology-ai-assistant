"""Tests de AssemblyAITranscriptionProvider. Nunca llama a la API real:
todo el transporte HTTP se sustituye por httpx.MockTransport."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.integrations.domain.transcription_provider import (
    AudioForTranscription,
    TranscriptionInput,
    TranscriptionSegment,
)
from app.integrations.providers.assemblyai_transcription_provider import (
    AssemblyAITranscriptionProvider,
)

_AUDIO_INPUT = TranscriptionInput(
    clinical_session_id=uuid.uuid4(),
    audio=AudioForTranscription(
        audio_bytes=b"contenido ficticio de audio",
        mime_type="audio/mpeg",
        filename="consulta_ficticia.mp3",
    ),
)


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.assemblyai.com"
    )


def _success_handler(seen_auth_headers: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("authorization", ""))
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        if request.url.path == "/v2/transcript/transcript-1":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "text": "El paciente refiere acúfenos.",
                    "language_code": "es",
                    "audio_duration": 12.5,
                    "confidence": 0.87,
                    "utterances": [
                        {"speaker": "A", "start": 0, "end": 4300, "text": "Buenos días."},
                        {"speaker": "B", "start": 4300, "end": 9000, "text": "Hola, doctor."},
                    ],
                },
            )
        raise AssertionError(f"petición inesperada: {request.method} {request.url}")

    return handler


async def test_transcribe_normaliza_la_respuesta_completa():
    seen_auth_headers: list[str] = []
    client = _client_with_handler(_success_handler(seen_auth_headers))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia-de-test", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.text == "El paciente refiere acúfenos."
    assert result.language == "es"
    assert result.duration_ms == 12500
    assert result.confidence == 87
    assert result.segments == [
        TranscriptionSegment(speaker="A", start_ms=0, end_ms=4300, text="Buenos días."),
        TranscriptionSegment(speaker="B", start_ms=4300, end_ms=9000, text="Hola, doctor."),
    ]
    assert all(header == "clave-ficticia-de-test" for header in seen_auth_headers)


async def test_hace_polling_hasta_completed():
    call_count = {"transcript_status": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        if request.url.path == "/v2/transcript/transcript-1":
            call_count["transcript_status"] += 1
            if call_count["transcript_status"] < 3:
                return httpx.Response(200, json={"status": "processing"})
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "text": "texto final",
                    "language_code": "es",
                    "audio_duration": 1.0,
                    "confidence": 0.5,
                    "utterances": [],
                },
            )
        raise AssertionError("petición inesperada")

    async def no_sleep(_seconds: float) -> None:
        return None

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0, sleep=no_sleep
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.text == "texto final"
    assert call_count["transcript_status"] == 3
    assert result.segments is None  # utterances vacío -> sin segmentos


async def test_status_error_lanza_excepcion_con_el_motivo():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200, json={"status": "error", "error": "audio_too_short (fixture de test)"}
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    with pytest.raises(RuntimeError, match="audio_too_short"):
        await provider.transcribe(_AUDIO_INPUT)


async def test_supera_el_timeout_de_polling():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(200, json={"status": "processing"})

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        poll_interval_seconds=0,
        poll_timeout_seconds=0,
    )

    with pytest.raises(TimeoutError):
        await provider.transcribe(_AUDIO_INPUT)


async def test_falla_una_llamada_http_propaga_el_error_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "fallo simulado del servidor"})

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.transcribe(_AUDIO_INPUT)


def test_sin_api_key_lanza_error_claro_en_la_construccion():
    with pytest.raises(ValueError, match="ASSEMBLYAI_API_KEY"):
        AssemblyAITranscriptionProvider(api_key=None)

    with pytest.raises(ValueError, match="ASSEMBLYAI_API_KEY"):
        AssemblyAITranscriptionProvider(api_key="")


async def test_sin_audio_lanza_error_claro():
    provider = AssemblyAITranscriptionProvider(api_key="clave-ficticia")
    input_sin_audio = TranscriptionInput(clinical_session_id=_AUDIO_INPUT.clinical_session_id)

    with pytest.raises(ValueError, match="audio real"):
        await provider.transcribe(input_sin_audio)


async def test_la_api_key_nunca_aparece_en_una_excepcion():
    secret = "super-secreta-no-debe-aparecer-en-ningun-error"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key=secret, http_client=client, poll_interval_seconds=0
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.transcribe(_AUDIO_INPUT)

    assert secret not in str(exc_info.value)
