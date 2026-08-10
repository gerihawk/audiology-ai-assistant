"""Tests de AssemblyAITranscriptionProvider. Nunca llama a la API real:
todo el transporte HTTP se sustituye por httpx.MockTransport."""

from __future__ import annotations

import json
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
                    "id": "transcript-1",
                    "status": "completed",
                    "text": "El paciente refiere acúfenos.",
                    "language_code": "es",
                    "audio_duration": 12.5,
                    "confidence": 0.87,
                    "speech_model": "best",
                    "punctuate": True,
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


async def test_captura_model_name_desde_speech_model():
    client = _client_with_handler(_success_handler([]))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.model_name == "best"


async def test_captura_provider_metadata_con_capacidades_activas_sin_raw_response_completo():
    client = _client_with_handler(_success_handler([]))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0, language_code="es"
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.provider_metadata == {
        "transcript_id": "transcript-1",
        "speaker_labels_requested": True,
        "diarization_used": True,
        "language_code_requested": "es",
        "language_code_detected": "es",
        "punctuate": True,
        "speech_models_requested": None,
        "speakers_expected_requested": None,
        "medical_mode": False,
        "keyterm_prompting": False,
        "keyterm_set_version": None,
    }
    # Nunca el raw_response completo: ni "text" ni "confidence" ni
    # "audio_duration" (ya viven en TranscriptionResult, no duplicados aquí).
    assert "text" not in result.provider_metadata
    assert "confidence" not in result.provider_metadata


async def test_model_name_es_none_si_ningun_campo_conocido_esta_presente():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "hola",
                "language_code": "es",
                "utterances": [],
            },
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.model_name is None  # nunca inventado


async def test_model_name_prueba_los_campos_alternativos_en_orden():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "hola",
                "language_code": "es",
                "language_model": "assemblyai_default",
                "utterances": [],
            },
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.model_name == "assemblyai_default"


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


# --- Perfil experimental (Fase 5.2) ---------------------------------------------


def _capture_request_body_handler(captured_body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            captured_body.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "hola",
                "language_code": "es",
                "utterances": [],
            },
        )

    return handler


async def test_perfil_baseline_no_envia_ningun_parametro_experimental():
    captured_body: dict = {}
    client = _client_with_handler(_capture_request_body_handler(captured_body))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    await provider.transcribe(_AUDIO_INPUT)

    assert captured_body == {
        "audio_url": "https://cdn.assemblyai.com/x",
        "language_code": "es",
        "speaker_labels": True,
    }


async def test_perfil_optimizado_envia_speech_models_speakers_expected_domain_y_keyterms():
    captured_body: dict = {}
    client = _client_with_handler(_capture_request_body_handler(captured_body))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        poll_interval_seconds=0,
        speech_models=["universal-3-5-pro"],
        speakers_expected=2,
        medical_mode=True,
        keyterms_prompt=["hipoacusia", "acúfenos"],
        keyterm_set_version="audiology-es-v1",
    )

    await provider.transcribe(_AUDIO_INPUT)

    assert captured_body == {
        "audio_url": "https://cdn.assemblyai.com/x",
        "language_code": "es",
        "speaker_labels": True,
        "speech_models": ["universal-3-5-pro"],
        "speakers_expected": 2,
        "domain": "medical-v1",
        "keyterms_prompt": ["hipoacusia", "acúfenos"],
    }


async def test_speakers_expected_none_no_se_envia_aunque_otras_opciones_esten_activas():
    captured_body: dict = {}
    client = _client_with_handler(_capture_request_body_handler(captured_body))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        poll_interval_seconds=0,
        medical_mode=True,
        speakers_expected=None,
    )

    await provider.transcribe(_AUDIO_INPUT)

    assert "speakers_expected" not in captured_body
    assert captured_body["domain"] == "medical-v1"


async def test_medical_mode_y_keyterms_se_registran_en_provider_metadata():
    client = _client_with_handler(_success_handler([]))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        poll_interval_seconds=0,
        medical_mode=True,
        keyterms_prompt=["hipoacusia"],
        keyterm_set_version="audiology-es-v1",
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.provider_metadata["medical_mode"] is True
    assert result.provider_metadata["keyterm_prompting"] is True
    assert result.provider_metadata["keyterm_set_version"] == "audiology-es-v1"


async def test_speech_models_y_speakers_expected_se_registran_en_provider_metadata():
    client = _client_with_handler(_success_handler([]))
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        poll_interval_seconds=0,
        speech_models=["universal-3-5-pro"],
        speakers_expected=2,
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.provider_metadata["speech_models_requested"] == ["universal-3-5-pro"]
    assert result.provider_metadata["speakers_expected_requested"] == 2


# --- Fallback de normalización: utterances -> words -> sin segmentos -----------


async def test_normaliza_desde_words_cuando_no_hay_utterances():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "Hola buenos días",
                "language_code": "es",
                "audio_duration": 2.0,
                "utterances": [],
                "words": [
                    {"text": "Hola", "speaker": "A", "start": 0, "end": 400},
                    {"text": "buenos", "speaker": "B", "start": 400, "end": 800},
                    {"text": "días", "speaker": "B", "start": 800, "end": 1200},
                ],
            },
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.segments == [
        TranscriptionSegment(speaker="A", start_ms=0, end_ms=400, text="Hola"),
        TranscriptionSegment(speaker="B", start_ms=400, end_ms=1200, text="buenos días"),
    ]


async def test_utterances_tiene_prioridad_sobre_words():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "Hola",
                "language_code": "es",
                "utterances": [
                    {"speaker": "A", "start": 0, "end": 500, "text": "Hola (utterance)"}
                ],
                "words": [{"text": "Hola", "speaker": "B", "start": 0, "end": 500}],
            },
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.segments == [
        TranscriptionSegment(speaker="A", start_ms=0, end_ms=500, text="Hola (utterance)")
    ]


async def test_sin_utterances_ni_words_con_speaker_no_genera_segmentos():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://cdn.assemblyai.com/x"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "text": "Hola",
                "language_code": "es",
                "utterances": [],
                "words": [{"text": "Hola", "start": 0, "end": 500}],  # sin "speaker"
            },
        )

    client = _client_with_handler(handler)
    provider = AssemblyAITranscriptionProvider(
        api_key="clave-ficticia", http_client=client, poll_interval_seconds=0
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.segments is None
