"""Tests de validación de subida de audio (tamaño/duración/extensión/MIME)."""

from __future__ import annotations

from app.audio.domain.validation import find_upload_validation_error
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "audio_max_size_mb": 10,
        "audio_allowed_mime_types": "audio/mpeg,audio/wav",
        "audio_allowed_extensions": "mp3,wav",
        "audio_max_duration_seconds": 600,
    }
    base.update(overrides)
    return Settings(**base)


def test_upload_valido_no_devuelve_error():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="mp3",
        size_bytes=1024,
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is None


def test_extension_no_permitida():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="exe",
        size_bytes=1024,
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is not None
    assert "extensión" in error.lower() or "extension" in error.lower()


def test_extension_con_punto_se_normaliza():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension=".mp3",
        size_bytes=1024,
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is None


def test_mime_type_no_permitido():
    error = find_upload_validation_error(
        mime_type="application/pdf",
        extension="mp3",
        size_bytes=1024,
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is not None
    assert "mime" in error.lower()


def test_fichero_vacio():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="mp3",
        size_bytes=0,
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is not None
    assert "vacío" in error.lower()


def test_supera_tamano_maximo():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="mp3",
        size_bytes=(11 * 1024 * 1024),
        duration_seconds=30,
        settings=_settings(),
    )
    assert error is not None
    assert "tamaño" in error.lower()


def test_duracion_cero_o_negativa():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="mp3",
        size_bytes=1024,
        duration_seconds=0,
        settings=_settings(),
    )
    assert error is not None
    assert "duración" in error.lower()


def test_supera_duracion_maxima():
    error = find_upload_validation_error(
        mime_type="audio/mpeg",
        extension="mp3",
        size_bytes=1024,
        duration_seconds=601,
        settings=_settings(),
    )
    assert error is not None
    assert "duración máxima" in error.lower()
