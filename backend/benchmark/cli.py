"""CLI del benchmark de transcripción — ver docs/transcription-benchmark.md.

Uso (dentro del contenedor backend, working dir /app):

    python -m benchmark.cli benchmark/audio/consulta_ficticia_01.mp3 --providers mock,assemblyai

Nunca ejecutar contra audios reales de pacientes — ver
benchmark/audio/README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import get_settings
from app.integrations.factory import TRANSCRIPTION_PROVIDER_FACTORIES
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from benchmark.report import build_report, write_report
from benchmark.runner import BenchmarkRunner

_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta el mismo audio contra varios proveedores de transcripción "
            "y compara resultados."
        )
    )
    parser.add_argument("audio_path", type=Path, help="Ruta al fichero de audio a transcribir.")
    parser.add_argument(
        "--providers",
        default="mock",
        help=(
            "Lista separada por comas de proveedores a comparar. Disponibles: "
            f"{', '.join(sorted(TRANSCRIPTION_PROVIDER_FACTORIES))}."
        ),
    )
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.audio_path.exists():
        print(f"No existe el fichero de audio: {args.audio_path}", file=sys.stderr)
        return 1

    provider_names = [name.strip() for name in args.providers.split(",") if name.strip()]
    settings = get_settings()
    runner = BenchmarkRunner(settings=settings)
    cost_estimator = MockCostEstimator()

    outcomes = await runner.run_many(provider_names, args.audio_path)

    header = f"{'proveedor':<12} {'ok':<4} {'ms':<8} {'palabras':<9} {'confianza':<10} resultado"
    print(header)
    print("-" * len(header))

    any_failed = False
    for outcome in outcomes:
        report = build_report(outcome, cost_estimator=cost_estimator, model_name=None)
        output_path = write_report(
            report,
            results_dir=_RESULTS_DIR,
            provider=outcome.provider,
            audio_file=outcome.audio_file,
        )
        confidence = report["confidence"]
        print(
            f"{outcome.provider:<12} {'sí' if outcome.succeeded else 'no':<4} "
            f"{outcome.response_time_ms:<8} {report['word_count']:<9} "
            f"{confidence if confidence is not None else '—':<10} {output_path}"
        )
        if outcome.error:
            any_failed = True
            print(f"    error: {outcome.error}")

    return 1 if any_failed else 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
