"""Comparación de todos los modelos disponibles para uno o varios
`case_id` del benchmark de generación — encargo de la Fase 6.2 §20-21.

Uso (dentro del contenedor backend, working dir /app):

    python -m benchmark.generation.compare consulta_ficticia_01__summary
    python -m benchmark.generation.compare consulta_ficticia_01__summary \\
        consulta_ficticia_01__missing_information \\
        consulta_ficticia_01__patient_summary

Nunca ejecuta ninguna generación — solo agrega resultados ya escritos por
`benchmark.generation.cli`. Selección de ganador jerárquica (encargo
§21): solo entran en juego los modelos que superan los 4 gates clínicos;
entre esos, gana quien tenga menos hallazgos MAJOR y, en empate, menor
coste — nunca al revés. **No fuerza un ganador global** (encargo,
precondición §13-14): con varios `case_id` (uno por `artifact_type`) solo
se declara un ganador global si el MISMO modelo gana en todos; si no,
`global_winner` queda `null` y `winners_by_artifact_type` muestra el
desglose real."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_RESULTS_DIR = Path(__file__).resolve().parent.parent / "generation_results"
_COMPARISONS_DIR = _RESULTS_DIR / "comparisons"


def _load_results_for(case_id: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not _RESULTS_DIR.is_dir():
        return results
    for profile_dir in sorted(_RESULTS_DIR.iterdir()):
        if not profile_dir.is_dir() or profile_dir.name == "comparisons":
            continue
        result_path = profile_dir / f"{case_id}.json"
        if result_path.exists():
            results[profile_dir.name] = json.loads(result_path.read_text(encoding="utf-8"))
    return results


def _findings_count(report: dict[str, Any], severity: str) -> int:
    return sum(1 for f in report.get("findings", []) if f.get("severity") == severity)


def build_comparison(case_id: str, results_by_profile: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    artifact_type = None
    for profile, report in sorted(results_by_profile.items()):
        artifact_type = artifact_type or report.get("artifact_type")
        gates = report.get("gates") or {}
        execution = report.get("execution") or {}
        rows.append(
            {
                "model_profile": profile,
                "model": report.get("model"),
                "passed_all_gates": gates.get("passed_all"),
                "blocking_gate": gates.get("blocking_gate"),
                "safety_gate": gates.get("safety_gate"),
                "hallucination_gate": gates.get("hallucination_gate"),
                "schema_gate": gates.get("schema_gate"),
                "negation_laterality_gate": gates.get("negation_laterality_gate"),
                "latency_ms": execution.get("latency_ms"),
                "input_tokens": execution.get("input_tokens"),
                "output_tokens": execution.get("output_tokens"),
                "estimated_cost_usd": execution.get("estimated_cost_usd"),
                "cost_source": execution.get("cost_source"),
                "findings_critical": _findings_count(report, "critical"),
                "findings_major": _findings_count(report, "major"),
                "findings_minor": _findings_count(report, "minor"),
            }
        )

    eligible = [row for row in rows if row["passed_all_gates"]]
    winner = None
    if eligible:
        winner = min(
            eligible,
            key=lambda row: (
                row["findings_major"],
                (
                    float(row["estimated_cost_usd"])
                    if row["estimated_cost_usd"] is not None
                    else float("inf")
                ),
                row["latency_ms"] or 0,
            ),
        )["model_profile"]

    return {"case_id": case_id, "artifact_type": artifact_type, "models": rows, "winner": winner}


def select_winner_per_artifact_type(
    comparisons_by_artifact_type: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    winners_by_artifact_type = {
        artifact_type: comparison["winner"]
        for artifact_type, comparison in comparisons_by_artifact_type.items()
    }
    all_winners = list(winners_by_artifact_type.values())
    # Ganador global solo si TODOS los artifact_type tienen ganador (nadie
    # con `None`) Y es el mismo modelo en todos — nunca se rellena un
    # hueco con el ganador de otro artifact_type.
    global_winner = (
        all_winners[0]
        if all_winners and all(w is not None for w in all_winners) and len(set(all_winners)) == 1
        else None
    )
    return {"winners_by_artifact_type": winners_by_artifact_type, "global_winner": global_winner}


def _fmt(value: Any) -> str:
    return str(value) if value is not None else "—"


def _print_table(comparison: dict[str, Any]) -> None:
    rows = comparison["models"]
    if not rows:
        print(f"No hay resultados de ningún modelo para '{comparison['case_id']}'.")
        return

    header = (
        f"{'modelo':<32} {'gates':<6} {'crit':<5} {'major':<6} {'minor':<6} "
        f"{'ms':<8} {'coste':<12} fuente"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        marker = " *" if row["model_profile"] == comparison["winner"] else ""
        print(
            f"{row['model_profile']:<32} {'sí' if row['passed_all_gates'] else 'no':<6} "
            f"{row['findings_critical']:<5} {row['findings_major']:<6} {row['findings_minor']:<6} "
            f"{_fmt(row['latency_ms']):<8} {_fmt(row['estimated_cost_usd']):<12} "
            f"{_fmt(row['cost_source'])}{marker}"
        )


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(
            "Uso: python -m benchmark.generation.compare <case_id> [<case_id> ...]", file=sys.stderr
        )
        sys.exit(1)

    _COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
    comparisons_by_artifact_type: dict[str, dict[str, Any]] = {}

    for case_id in argv:
        comparison = build_comparison(case_id, _load_results_for(case_id))
        _print_table(comparison)
        if comparison["artifact_type"]:
            comparisons_by_artifact_type[comparison["artifact_type"]] = comparison

        output_path = _COMPARISONS_DIR / f"{case_id}.json"
        output_path.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON agregado: {output_path}\n")

    if len(argv) > 1:
        summary = select_winner_per_artifact_type(comparisons_by_artifact_type)
        summary_path = _COMPARISONS_DIR / "summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Resumen multi-artifact_type (nunca fuerza un ganador global):")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
