"""Tests de benchmark/runner.py. Nunca AssemblyAI real: el caso
"assemblyai" se ejercita deliberadamente sin API key, para comprobar que
un proveedor mal configurado se captura como error del outcome, nunca
aborta el benchmark completo ni lanza una excepción."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from benchmark.dataset import DatasetCase
from benchmark.runner import BenchmarkRunner


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
def case(tmp_path) -> DatasetCase:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"contenido ficticio de audio de benchmark, nunca un paciente real")
    return DatasetCase(
        id="consulta_ficticia_01", audio_path=audio_path, reference=None, metadata=None
    )


async def test_run_one_con_mock_devuelve_un_resultado_normalizado(case: DatasetCase):
    runner = BenchmarkRunner(settings=_settings())
    outcome = await runner.run_one("mock", case)

    assert outcome.succeeded is True
    assert outcome.provider == "mock"
    assert outcome.audio_id == "consulta_ficticia_01"
    assert outcome.result is not None
    assert outcome.result.text
    assert outcome.response_time_ms >= 0


async def test_run_one_con_proveedor_desconocido_no_lanza_captura_el_error(case: DatasetCase):
    runner = BenchmarkRunner(settings=_settings())
    outcome = await runner.run_one("deepgram", case)

    assert outcome.succeeded is False
    assert outcome.result is None
    assert "deepgram" in outcome.error


async def test_run_one_con_assemblyai_mal_configurado_captura_el_error_sin_red(case: DatasetCase):
    """Nunca llama a la red: falta ASSEMBLYAI_API_KEY, así que
    build_transcription_provider lanza antes de que exista cualquier
    posibilidad de una petición HTTP real."""
    runner = BenchmarkRunner(settings=_settings(transcription_provider="assemblyai"))
    outcome = await runner.run_one("assemblyai", case)

    assert outcome.succeeded is False
    assert "ASSEMBLYAI_API_KEY" in outcome.error


async def test_run_many_ejecuta_todos_los_proveedores_pedidos_pese_a_fallos(case: DatasetCase):
    runner = BenchmarkRunner(settings=_settings())
    outcomes = await runner.run_many(["mock", "deepgram"], case)

    assert [o.provider for o in outcomes] == ["mock", "deepgram"]
    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False
