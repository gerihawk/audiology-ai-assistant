"""CLI del benchmark de generación — ver docs/generation-benchmark.md.

Uso (dentro del contenedor backend, working dir /app):

    python -m benchmark.generation.cli consulta_ficticia_01__summary \\
        --models openai/gpt-...,anthropic/claude-...

Requiere `GENERATION_BENCHMARK_ENABLED=true` y `OPENROUTER_API_KEY`
configuradas — falla explícitamente si faltan (nunca una llamada anónima
ni un fallback silencioso a otro proveedor). Se niega a invocar un modelo
real si el caso no tiene `reference.json` con contenido (ver
`runner.GenerationReferenceRequiredError`). Ejecución secuencial, nunca
concurrente (encargo §17)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.core import orm_registry  # noqa: F401 — registra los modelos ORM
from app.core.config import Settings, get_settings
from app.core.db import get_session_factory
from benchmark.generation.dataset import GenerationCaseNotFoundError, load_generation_case
from benchmark.generation.report import build_result, write_result
from benchmark.generation.runner import GenerationBenchmarkRunner, GenerationReferenceRequiredError

_DATASET_DIR = Path(__file__).resolve().parent.parent / "generation_dataset"
_RESULTS_DIR = Path(__file__).resolve().parent.parent / "generation_results"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta un caso del dataset de generación contra varios modelos de OpenRouter."
    )
    parser.add_argument(
        "case_id", help="Identificador del caso en benchmark/generation_dataset/<case_id>/."
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Lista separada por comas de model id exactos de OpenRouter.",
    )
    return parser.parse_args(argv)


def _require_enabled(settings: Settings) -> None:
    if not settings.generation_benchmark_enabled:
        raise SystemExit(
            "GENERATION_BENCHMARK_ENABLED=false — actívala explícitamente para ejecutar "
            "el benchmark de generación."
        )
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY no configurada — obligatoria para este benchmark.")


def _model_profile(model: str) -> str:
    return model.replace("/", "__")


async def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    _require_enabled(settings)

    try:
        case = load_generation_case(_DATASET_DIR, args.case_id)
    except GenerationCaseNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    header = f"{'modelo':<40} {'ok':<4} {'ms':<8} {'gates':<6} resultado"
    print(header)
    print("-" * len(header))

    any_failed = False
    session_factory = get_session_factory()
    async with session_factory() as session:
        runner = GenerationBenchmarkRunner(
            settings=settings,
            prompt_template_repository=SqlAlchemyPromptTemplateRepository(),
            db_session=session,
        )
        for model in models:
            try:
                outcome = await runner.run_one(case, model=model)
            except GenerationReferenceRequiredError as exc:
                print(str(exc), file=sys.stderr)
                return 1

            model_profile = _model_profile(model)
            result = build_result(outcome, model_profile=model_profile)
            output_path = write_result(
                result, results_dir=_RESULTS_DIR, model_profile=model_profile, case_id=case.id
            )

            any_failed = any_failed or not outcome.succeeded
            print(
                f"{model:<40} {'sí' if outcome.succeeded else 'no':<4} {outcome.latency_ms:<8} "
                f"{'sí' if outcome.gates.passed_all else 'no':<6} {output_path}"
            )
            if not outcome.succeeded:
                print(f"    fallo: {result['execution']['failure_reason']}")

    return 1 if any_failed else 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
