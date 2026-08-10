"""Tests de benchmark/runner.py y benchmark/report.py. Nunca AssemblyAI real:
el caso "assemblyai" se ejercita deliberadamente sin API key, para
comprobar que un proveedor mal configurado se captura como error del
outcome, nunca aborta el benchmark completo ni lanza una excepción."""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from benchmark.report import build_report, write_report
from benchmark.runner import BenchmarkOutcome, BenchmarkRunner


def _settings(**overrides) -> Settings:
    base = {
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "transcription_provider": "mock",
        "assemblyai_api_key": None,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "consulta_ficticia_01.mp3"
    path.write_bytes(b"contenido ficticio de audio de benchmark, nunca un paciente real")
    return path


# --- BenchmarkRunner -----------------------------------------------------------


async def test_run_one_con_mock_devuelve_un_resultado_normalizado(audio_file):
    runner = BenchmarkRunner(settings=_settings())
    outcome = await runner.run_one("mock", audio_file)

    assert outcome.succeeded is True
    assert outcome.provider == "mock"
    assert outcome.audio_file == "consulta_ficticia_01.mp3"
    assert outcome.result is not None
    assert outcome.result.text
    assert outcome.response_time_ms >= 0


async def test_run_one_con_proveedor_desconocido_no_lanza_captura_el_error(audio_file):
    runner = BenchmarkRunner(settings=_settings())
    outcome = await runner.run_one("deepgram", audio_file)

    assert outcome.succeeded is False
    assert outcome.result is None
    assert "deepgram" in outcome.error


async def test_run_one_con_assemblyai_mal_configurado_captura_el_error_sin_red(audio_file):
    """Nunca llama a la red: falta ASSEMBLYAI_API_KEY, así que
    build_transcription_provider lanza antes de que exista cualquier
    posibilidad de una petición HTTP real."""
    runner = BenchmarkRunner(settings=_settings(transcription_provider="assemblyai"))
    outcome = await runner.run_one("assemblyai", audio_file)

    assert outcome.succeeded is False
    assert "ASSEMBLYAI_API_KEY" in outcome.error


async def test_run_many_ejecuta_todos_los_proveedores_pedidos_pese_a_fallos(audio_file):
    runner = BenchmarkRunner(settings=_settings())
    outcomes = await runner.run_many(["mock", "deepgram"], audio_file)

    assert [o.provider for o in outcomes] == ["mock", "deepgram"]
    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False


# --- report.py -------------------------------------------------------------------


def _success_outcome() -> BenchmarkOutcome:
    from app.integrations.domain.transcription_provider import (
        TranscriptionResult,
        TranscriptionSegment,
    )

    return BenchmarkOutcome(
        provider="mock",
        audio_file="consulta_ficticia_01.mp3",
        ran_at="2026-01-01T00:00:00+00:00",
        response_time_ms=42,
        result=TranscriptionResult(
            text="El paciente refiere acúfenos leves.",
            language="es",
            confidence=70,
            duration_ms=8000,
            segments=[
                TranscriptionSegment(speaker="A", start_ms=0, end_ms=4000, text="Hola."),
                TranscriptionSegment(speaker="B", start_ms=4000, end_ms=8000, text="Buenos días."),
            ],
        ),
        error=None,
    )


def _failure_outcome() -> BenchmarkOutcome:
    return BenchmarkOutcome(
        provider="deepgram",
        audio_file="consulta_ficticia_01.mp3",
        ran_at="2026-01-01T00:00:00+00:00",
        response_time_ms=5,
        result=None,
        error="'deepgram' no es un proveedor de transcripción reconocido.",
    )


def test_build_report_incluye_todas_las_metricas_esperadas():
    report = build_report(_success_outcome(), cost_estimator=MockCostEstimator(), model_name=None)

    assert report["provider"] == "mock"
    assert report["succeeded"] is True
    assert report["error"] is None
    assert report["response_time_ms"] == 42
    assert report["audio_duration_ms"] == 8000
    assert report["detected_language"] == "es"
    expected_words = ["El", "paciente", "refiere", "acúfenos", "leves."]
    assert report["word_count"] == len(expected_words)
    assert report["has_timestamps"] is True
    assert report["diarization_available"] is True
    assert report["segment_count"] == 2
    assert report["confidence"] == 70
    assert report["wer"] is None  # preparado, no calculado en esta fase


def test_build_report_para_un_fallo_no_tiene_metricas_de_contenido():
    report = build_report(_failure_outcome(), cost_estimator=MockCostEstimator(), model_name=None)

    assert report["succeeded"] is False
    assert "no es un proveedor" in report["error"]
    assert report["word_count"] == 0
    assert report["has_timestamps"] is False
    assert report["diarization_available"] is False
    assert report["segment_count"] == 0
    assert report["text"] is None


def test_write_report_escribe_json_en_la_carpeta_del_proveedor(tmp_path):
    report = build_report(_success_outcome(), cost_estimator=MockCostEstimator(), model_name=None)
    output_path = write_report(
        report, results_dir=tmp_path, provider="mock", audio_file="consulta_ficticia_01.mp3"
    )

    assert output_path == tmp_path / "mock" / "consulta_ficticia_01.json"
    assert output_path.exists()
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["provider"] == "mock"
    assert persisted["text"] == "El paciente refiere acúfenos leves."


def test_write_report_de_dos_proveedores_para_el_mismo_audio_no_se_pisan(tmp_path):
    cost_estimator = MockCostEstimator()
    mock_report = build_report(_success_outcome(), cost_estimator=cost_estimator, model_name=None)
    other_outcome = _success_outcome()
    other_outcome.provider = "assemblyai"

    write_report(mock_report, results_dir=tmp_path, provider="mock", audio_file="audio.mp3")
    assemblyai_report = build_report(other_outcome, cost_estimator=cost_estimator, model_name=None)
    write_report(
        assemblyai_report, results_dir=tmp_path, provider="assemblyai", audio_file="audio.mp3"
    )

    assert (tmp_path / "mock" / "audio.json").exists()
    assert (tmp_path / "assemblyai" / "audio.json").exists()
