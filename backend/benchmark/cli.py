"""CLI del benchmark de transcripción — ver docs/transcription-benchmark.md.

Uso (dentro del contenedor backend, working dir /app):

    python -m benchmark.cli consulta_ficticia_01 --providers mock,assemblyai

Resuelve el caso desde `benchmark/dataset/<audio_id>/` (audio obligatorio;
`reference.json`/`metadata.json` opcionales — sin ellos se generan menos
métricas, nunca un error). Nunca ejecutar contra audios reales de
pacientes — ver benchmark/dataset/README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.integrations.factory import TRANSCRIPTION_PROVIDER_FACTORIES, build_audio_cost_estimator
from benchmark.dataset import DatasetCase, DatasetCaseNotFoundError, load_dataset_case
from benchmark.report import build_report, write_report
from benchmark.runner import BenchmarkOutcome, BenchmarkRunner

_DATASET_DIR = Path(__file__).resolve().parent / "dataset"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta un caso del dataset contra varios proveedores de "
            "transcripción y compara resultados."
        )
    )
    parser.add_argument("audio_id", help="Identificador del caso en benchmark/dataset/<audio_id>/.")
    parser.add_argument(
        "--providers",
        default="mock",
        help=(
            "Lista separada por comas de proveedores a comparar. Disponibles: "
            f"{', '.join(sorted(TRANSCRIPTION_PROVIDER_FACTORIES))}."
        ),
    )
    return parser.parse_args(argv)


def _report_for(outcome: BenchmarkOutcome, *, settings: Settings, case: DatasetCase) -> dict:
    cost_estimator = build_audio_cost_estimator(settings, outcome.provider)
    result = outcome.result
    if result is not None and result.duration_ms is not None:
        # Los componentes activos vienen del propio provider_metadata (Fase
        # 5.1) — el mismo dato usado para trazabilidad de modelo alimenta
        # también el coste por componentes, sin una segunda fuente de
        # verdad que pueda divergir (ver docs/transcription-benchmark.md
        # §Pricing).
        provider_metadata = result.provider_metadata or {}
        cost_estimate = cost_estimator.estimate(
            provider=outcome.provider,
            model=result.model_name,
            audio_duration_seconds=result.duration_ms / 1000,
            diarization=bool(provider_metadata.get("speaker_labels_requested")),
            medical_mode=bool(provider_metadata.get("medical_mode")),
            keyterms_prompt=bool(provider_metadata.get("keyterm_prompting")),
        )
        estimated_cost_usd = str(cost_estimate.amount_usd)
        estimated_cost_source = cost_estimate.source.value
        pricing_version = cost_estimate.pricing_version
        pricing_effective_date = cost_estimate.pricing_effective_date
    else:
        estimated_cost_usd = "0"
        estimated_cost_source = "mock"
        pricing_version = None
        pricing_effective_date = None

    return build_report(
        outcome,
        estimated_cost_usd=estimated_cost_usd,
        estimated_cost_source=estimated_cost_source,
        pricing_version=pricing_version,
        pricing_effective_date=pricing_effective_date,
        reference=case.reference,
        metadata=case.metadata,
    )


async def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        case = load_dataset_case(_DATASET_DIR, args.audio_id)
    except DatasetCaseNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    provider_names = [name.strip() for name in args.providers.split(",") if name.strip()]
    settings = get_settings()
    runner = BenchmarkRunner(settings=settings)

    outcomes = await runner.run_many(provider_names, case)

    header = f"{'proveedor':<12} {'ok':<4} {'ms':<8} {'palabras':<9} {'wer':<8} resultado"
    print(header)
    print("-" * len(header))

    any_failed = False
    for outcome in outcomes:
        report = _report_for(outcome, settings=settings, case=case)
        output_path = write_report(
            report, results_dir=_RESULTS_DIR, provider=outcome.provider, audio_id=case.id
        )
        wer = report["metrics"]["wer"]
        wer_display = f"{wer['value']:.2f}" if wer else "—"
        print(
            f"{outcome.provider:<12} {'sí' if outcome.succeeded else 'no':<4} "
            f"{outcome.response_time_ms:<8} {report['transcription']['word_count']:<9} "
            f"{wer_display:<8} {output_path}"
        )
        if outcome.error:
            any_failed = True
            print(f"    error: {outcome.error}")

    if not case.reference:
        print(
            "\n(sin reference.json — WER/terminología no calculados, "
            "ver docs/transcription-benchmark.md)"
        )
    if not case.metadata:
        print("(sin metadata.json — negaciones/lateralidad no evaluadas)")

    return 1 if any_failed else 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
