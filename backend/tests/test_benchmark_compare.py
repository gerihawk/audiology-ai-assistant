"""Tests de benchmark/compare.py — agregación de resultados ya generados
(nunca ejecuta ninguna transcripción, solo lee JSON de disco)."""

from __future__ import annotations

import json

from benchmark.compare import build_comparison, main


def _report(provider: str, **overrides) -> dict:
    base = {
        "provider": provider,
        "model": "mock-v1",
        "audio_id": "consulta_ficticia_01",
        "processing_time_ms": 100,
        "real_time_factor": 0.1,
        "estimated_cost_usd": "0",
        "estimated_cost_source": "mock",
        "metrics": {
            "wer": {
                "value": 0.1,
                "substitutions": 1,
                "deletions": 0,
                "insertions": 0,
                "reference_word_count": 10,
            },
            "terminology": {"accuracy": 0.9, "details": []},
            "negations": {"passed": 2, "failed": 0, "details": []},
            "laterality": {"passed": 1, "failed": 0, "details": []},
            "diarization": {
                "reference_speaker_count": 2,
                "detected_speaker_count": 2,
                "speaker_count_match": True,
                "attribution_accuracy": 1.0,
                "number_of_reference_segments": 4,
                "number_of_provider_segments": 4,
            },
        },
    }
    base.update(overrides)
    return base


def test_build_comparison_extrae_las_columnas_clave():
    reports = {
        "mock": _report("mock"),
        "assemblyai": _report(
            "assemblyai",
            model="best",
            metrics={
                **_report("assemblyai")["metrics"],
                "wer": {
                    "value": 0.05,
                    "substitutions": 0,
                    "deletions": 1,
                    "insertions": 0,
                    "reference_word_count": 20,
                },
                "diarization": {
                    "reference_speaker_count": 2,
                    "detected_speaker_count": 1,
                    "speaker_count_match": False,
                    "attribution_accuracy": None,
                    "number_of_reference_segments": 4,
                    "number_of_provider_segments": 1,
                },
            },
        ),
    }
    comparison = build_comparison("consulta_ficticia_01", reports)

    assert comparison["audio_id"] == "consulta_ficticia_01"
    providers = {row["provider"]: row for row in comparison["providers"]}
    assert providers["mock"]["wer"] == 0.1
    assert providers["assemblyai"]["wer"] == 0.05
    assert providers["assemblyai"]["detected_speakers"] == 1
    assert providers["mock"]["detected_speakers"] == 2


def test_build_comparison_sin_metricas_no_falla():
    reports = {"mock": {"provider": "mock", "model": None, "metrics": None}}
    comparison = build_comparison("audio_x", reports)
    row = comparison["providers"][0]
    assert row["wer"] is None
    assert row["detected_speakers"] is None


def test_build_comparison_sin_resultados_devuelve_lista_vacia():
    comparison = build_comparison("no_existe", {})
    assert comparison["providers"] == []


def test_main_lee_resultados_de_disco_y_escribe_json_agregado(tmp_path, monkeypatch):
    results_dir = tmp_path / "results"
    (results_dir / "mock").mkdir(parents=True)
    (results_dir / "mock" / "consulta_ficticia_01.json").write_text(
        json.dumps(_report("mock")), encoding="utf-8"
    )

    import benchmark.compare as compare_module

    monkeypatch.setattr(compare_module, "_RESULTS_DIR", results_dir)
    monkeypatch.setattr(compare_module, "_COMPARISONS_DIR", results_dir / "comparisons")

    main(["consulta_ficticia_01"])

    output_path = results_dir / "comparisons" / "consulta_ficticia_01.json"
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["providers"][0]["provider"] == "mock"


def test_main_ignora_la_carpeta_de_comparaciones_como_si_fuera_proveedor(tmp_path, monkeypatch):
    results_dir = tmp_path / "results"
    (results_dir / "comparisons").mkdir(parents=True)
    (results_dir / "comparisons" / "otro_audio.json").write_text("{}", encoding="utf-8")

    import benchmark.compare as compare_module

    monkeypatch.setattr(compare_module, "_RESULTS_DIR", results_dir)
    monkeypatch.setattr(compare_module, "_COMPARISONS_DIR", results_dir / "comparisons")

    comparison = compare_module.build_comparison(
        "otro_audio", compare_module._load_results_for("otro_audio")
    )
    assert comparison["providers"] == []
