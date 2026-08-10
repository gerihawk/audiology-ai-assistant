"""Comparación de todos los proveedores disponibles para un mismo
`audio_id` — ver docs/transcription-benchmark.md §Comparison report.

Uso (dentro del contenedor backend, working dir /app):

    python -m benchmark.compare consulta_ficticia_01

Lee `benchmark/results/<provider>/<audio_id>.json` de cada proveedor que
tenga resultado para ese audio (nunca ejecuta ninguna transcripción — solo
agrega resultados ya generados por `benchmark/cli.py`), imprime una tabla
comparativa por terminal y escribe un JSON agregado en
`benchmark/results/comparisons/<audio_id>.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_COMPARISONS_DIR = _RESULTS_DIR / "comparisons"


def _load_results_for(audio_id: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not _RESULTS_DIR.is_dir():
        return results
    for provider_dir in sorted(_RESULTS_DIR.iterdir()):
        if not provider_dir.is_dir() or provider_dir.name == "comparisons":
            continue
        result_path = provider_dir / f"{audio_id}.json"
        if result_path.exists():
            results[provider_dir.name] = json.loads(result_path.read_text(encoding="utf-8"))
    return results


def build_comparison(
    audio_id: str, results_by_provider: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for provider, report in sorted(results_by_provider.items()):
        metrics = report.get("metrics") or {}
        wer = metrics.get("wer")
        terminology = metrics.get("terminology")
        negations = metrics.get("negations")
        laterality = metrics.get("laterality")
        diarization = metrics.get("diarization") or {}
        rows.append(
            {
                "provider": provider,
                "model": report.get("model"),
                "wer": wer["value"] if wer else None,
                "terminology_accuracy": terminology["accuracy"] if terminology else None,
                "negation_failures": negations["failed"] if negations else None,
                "laterality_failures": laterality["failed"] if laterality else None,
                "detected_speakers": diarization.get("detected_speaker_count"),
                "processing_time_ms": report.get("processing_time_ms"),
                "real_time_factor": report.get("real_time_factor"),
                "estimated_cost_usd": report.get("estimated_cost_usd"),
                "estimated_cost_source": report.get("estimated_cost_source"),
            }
        )
    return {"audio_id": audio_id, "providers": rows}


def _fmt_float(value: Any) -> str:
    return f"{value:.2f}" if isinstance(value, int | float) else "—"


def _fmt_plain(value: Any) -> str:
    return str(value) if value is not None else "—"


def _print_table(comparison: dict[str, Any]) -> None:
    rows = comparison["providers"]
    if not rows:
        print(f"No hay resultados de ningún proveedor para '{comparison['audio_id']}'.")
        return

    header = (
        f"{'proveedor':<12} {'modelo':<14} {'wer':<7} {'term.':<7} {'neg.fail':<9} "
        f"{'lat.fail':<9} {'speakers':<9} {'ms':<8} {'rtf':<7} {'coste':<10} fuente"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['provider']:<12} {_fmt_plain(row['model']):<14} "
            f"{_fmt_float(row['wer']):<7} {_fmt_float(row['terminology_accuracy']):<7} "
            f"{_fmt_plain(row['negation_failures']):<9} "
            f"{_fmt_plain(row['laterality_failures']):<9} "
            f"{_fmt_plain(row['detected_speakers']):<9} {_fmt_plain(row['processing_time_ms']):<8} "
            f"{_fmt_float(row['real_time_factor']):<7} {_fmt_plain(row['estimated_cost_usd']):<10} "
            f"{_fmt_plain(row['estimated_cost_source'])}"
        )


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("Uso: python -m benchmark.compare <audio_id>", file=sys.stderr)
        sys.exit(1)
    audio_id = argv[0]

    results_by_provider = _load_results_for(audio_id)
    comparison = build_comparison(audio_id, results_by_provider)
    _print_table(comparison)

    _COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _COMPARISONS_DIR / f"{audio_id}.json"
    output_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON agregado: {output_path}")


if __name__ == "__main__":
    main()
