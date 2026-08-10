"""Tests de DeepgramTranscriptionProvider. Nunca llama a la API real:
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
from app.integrations.providers.deepgram_transcription_provider import (
    DeepgramTranscriptionProvider,
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
        transport=httpx.MockTransport(handler), base_url="https://api.eu.deepgram.com"
    )


def _success_response(**overrides) -> dict:
    base = {
        "metadata": {
            "request_id": "req-1",
            "duration": 12.5,
            "models": ["model-uuid-1"],
            "model_info": {
                "model-uuid-1": {"name": "nova-3", "version": "2026-01-01.0", "arch": "nova-3"}
            },
        },
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Buenos días. Hola, doctor.",
                            "confidence": 0.94,
                            "words": [
                                {
                                    "word": "buenos",
                                    "punctuated_word": "Buenos",
                                    "start": 0.0,
                                    "end": 0.4,
                                    "confidence": 0.99,
                                    "speaker": 0,
                                },
                                {
                                    "word": "días",
                                    "punctuated_word": "días.",
                                    "start": 0.4,
                                    "end": 0.8,
                                    "confidence": 0.98,
                                    "speaker": 0,
                                },
                            ],
                        }
                    ]
                }
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "start": 0.0,
                    "end": 4.3,
                    "transcript": "Buenos días.",
                    "confidence": 0.95,
                },
                {
                    "speaker": 1,
                    "start": 4.3,
                    "end": 9.0,
                    "transcript": "Hola, doctor.",
                    "confidence": 0.9,
                },
            ],
        },
    }
    base.update(overrides)
    return base


def _success_handler(seen_auth_headers: list[str], response: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("authorization", ""))
        assert request.url.path == "/v1/listen"
        return httpx.Response(200, json=response if response is not None else _success_response())

    return handler


async def test_transcribe_normaliza_desde_utterances():
    seen_auth_headers: list[str] = []
    client = _client_with_handler(_success_handler(seen_auth_headers))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia-de-test", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.text == "Buenos días. Hola, doctor."
    assert result.language == "es"
    assert result.duration_ms == 12500
    assert result.confidence == 94
    assert result.segments == [
        TranscriptionSegment(speaker="0", start_ms=0, end_ms=4300, text="Buenos días."),
        TranscriptionSegment(speaker="1", start_ms=4300, end_ms=9000, text="Hola, doctor."),
    ]
    assert all(header == "Token clave-ficticia-de-test" for header in seen_auth_headers)


async def test_timestamps_se_convierten_de_segundos_a_milisegundos():
    # Deepgram devuelve start/end en segundos, no en ms (a diferencia de
    # AssemblyAI) — 4.3s debe convertirse en 4300ms, nunca quedarse en 4.
    client = _client_with_handler(_success_handler([]))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 4300
    assert isinstance(result.segments[0].end_ms, int)


async def test_normaliza_desde_words_cuando_no_hay_utterances():
    response = _success_response()
    response["results"]["utterances"] = []
    client = _client_with_handler(_success_handler([], response))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    # Agrupa palabras consecutivas del mismo hablante (ambas speaker=0 en
    # el fixture) usando punctuated_word cuando existe.
    assert result.segments == [
        TranscriptionSegment(speaker="0", start_ms=0, end_ms=800, text="Buenos días."),
    ]


async def test_utterances_tiene_prioridad_sobre_words():
    response = _success_response()
    # Las words del fixture son todas speaker=0; utterances tiene 2 speakers.
    client = _client_with_handler(_success_handler([], response))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert len(result.segments) == 2
    assert result.segments[1].speaker == "1"


async def test_sin_utterances_ni_words_con_speaker_no_genera_segmentos():
    response = _success_response()
    response["results"]["utterances"] = []
    for word in response["results"]["channels"][0]["alternatives"][0]["words"]:
        word.pop("speaker", None)
    client = _client_with_handler(_success_handler([], response))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.segments is None


async def test_captura_model_name_y_version():
    client = _client_with_handler(_success_handler([]))
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.model_name == "nova-3"
    assert result.provider_metadata["model_version"] == "2026-01-01.0"
    assert result.provider_metadata["model_arch"] == "nova-3"


async def test_provider_metadata_sin_raw_response_completo():
    client = _client_with_handler(_success_handler([]))
    provider = DeepgramTranscriptionProvider(
        api_key="clave-ficticia", http_client=client, language_code="es"
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.provider_metadata == {
        "request_id": "req-1",
        "model_version": "2026-01-01.0",
        "model_arch": "nova-3",
        "diarization_requested": True,
        "diarization_used": True,
        "smart_format_requested": True,
        "language_code_requested": "es",
        "keyterm_prompting": False,
        "keyterm_set_version": None,
        "api_base": "https://api.eu.deepgram.com",
        "region": "eu",
    }
    assert "transcript" not in result.provider_metadata
    assert "confidence" not in result.provider_metadata


async def test_region_us_si_el_base_url_no_es_eu():
    client = _client_with_handler(_success_handler([]))
    provider = DeepgramTranscriptionProvider(
        api_key="clave-ficticia", base_url="https://api.deepgram.com", http_client=client
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    assert result.provider_metadata["region"] == "us"
    assert result.provider_metadata["api_base"] == "https://api.deepgram.com"


async def test_endpoint_eu_es_el_valor_por_defecto():
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia")
    assert "eu.deepgram.com" in provider._base_url


# --- Petición HTTP: parámetros y cuerpo -----------------------------------------


async def test_envia_el_audio_como_cuerpo_binario_sin_paso_de_subida_previo():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        captured["params"] = list(request.url.params.multi_items())
        return httpx.Response(200, json=_success_response())

    client = _client_with_handler(handler)
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    await provider.transcribe(_AUDIO_INPUT)

    assert captured["content_type"] == "audio/mpeg"
    assert captured["body"] == b"contenido ficticio de audio"
    assert ("model", "nova-3") in captured["params"]
    assert ("language", "es") in captured["params"]
    assert ("diarize", "true") in captured["params"]
    assert ("utterances", "true") in captured["params"]
    assert ("smart_format", "true") in captured["params"]
    assert ("punctuate", "true") in captured["params"]
    assert not any(key == "keyterm" for key, _ in captured["params"])


async def test_keyterms_se_repiten_como_parametro_multiple():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = list(request.url.params.multi_items())
        return httpx.Response(200, json=_success_response())

    client = _client_with_handler(handler)
    provider = DeepgramTranscriptionProvider(
        api_key="clave-ficticia",
        http_client=client,
        keyterms=["hipoacusia", "acúfenos"],
        keyterm_set_version="audiology-es-v1",
    )

    result = await provider.transcribe(_AUDIO_INPUT)

    keyterm_values = [value for key, value in captured["params"] if key == "keyterm"]
    assert keyterm_values == ["hipoacusia", "acúfenos"]
    assert result.provider_metadata["keyterm_prompting"] is True
    assert result.provider_metadata["keyterm_set_version"] == "audiology-es-v1"


# --- Errores, timeout, secretos --------------------------------------------------


async def test_error_http_propaga_httpstatuserror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"err_code": "INVALID_AUTH", "err_msg": "unauthorized"})

    client = _client_with_handler(handler)
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia", http_client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.transcribe(_AUDIO_INPUT)


async def test_timeout_de_la_peticion_se_propaga():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tiempo agotado (fixture de test)")

    client = _client_with_handler(handler)
    provider = DeepgramTranscriptionProvider(
        api_key="clave-ficticia", http_client=client, timeout_seconds=0.01
    )

    with pytest.raises(httpx.TimeoutException):
        await provider.transcribe(_AUDIO_INPUT)


async def test_sin_api_key_lanza_error_claro_en_la_construccion():
    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        DeepgramTranscriptionProvider(api_key=None)

    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        DeepgramTranscriptionProvider(api_key="")


async def test_sin_audio_lanza_error_claro():
    provider = DeepgramTranscriptionProvider(api_key="clave-ficticia")
    input_sin_audio = TranscriptionInput(clinical_session_id=_AUDIO_INPUT.clinical_session_id)

    with pytest.raises(ValueError, match="audio real"):
        await provider.transcribe(input_sin_audio)


async def test_la_api_key_nunca_aparece_en_una_excepcion():
    secret = "super-secreta-no-debe-aparecer-en-ningun-error"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"err_msg": "unauthorized"})

    client = _client_with_handler(handler)
    provider = DeepgramTranscriptionProvider(api_key=secret, http_client=client)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.transcribe(_AUDIO_INPUT)

    assert secret not in str(exc_info.value)


async def test_la_api_key_nunca_aparece_en_json_dumps_de_provider_metadata():
    client = _client_with_handler(_success_handler([]))
    secret = "super-secreta-de-verificacion"
    provider = DeepgramTranscriptionProvider(api_key=secret, http_client=client)

    result = await provider.transcribe(_AUDIO_INPUT)

    assert secret not in json.dumps(result.provider_metadata)
