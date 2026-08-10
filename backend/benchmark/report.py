"""Construcción y persistencia del informe JSON de cada ejecución de benchmark.

Ver docs/transcription-benchmark.md §Métricas y §Formato de resultados.
`wer` queda preparado (`None`) pero no se calcula todavía — requiere una
transcripción de referencia que este MVP no tiene (ver Backlog en el doc).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.integrations.domain.cost_estimator import CostEstimator
from benchmark.runner import BenchmarkOutcome


def build_report(
    outcome: BenchmarkOutcome, *, cost_estimator: CostEstimator, model_name: str | None
) -> dict[str, Any]:
    result = outcome.result
    text = result.text if result else None
    word_count = len(text.split()) if text else 0
    segments = result.segments if result else None

    estimated_cost_usd = None
    if result is not None:
        # Aproximación: el benchmark no tiene un TokenCounter específico de
        # audio, usa el recuento de palabras como proxy de "tokens de
        # salida" — suficiente para comparar orden de magnitud entre
        # proveedores, no para facturación real (ver docs/transcription-benchmark.md).
        cost = cost_estimator.estimate(
            provider=outcome.provider, model=model_name, input_tokens=0, output_tokens=word_count
        )
        estimated_cost_usd = str(cost)

    return {
        "provider": outcome.provider,
        "model": model_name,
        "audio_file": outcome.audio_file,
        "ran_at": outcome.ran_at,
        "succeeded": outcome.succeeded,
        "error": outcome.error,
        "response_time_ms": outcome.response_time_ms,
        "audio_duration_ms": result.duration_ms if result else None,
        "detected_language": result.language if result else None,
        "estimated_cost_usd": estimated_cost_usd,
        "word_count": word_count,
        "has_timestamps": bool(segments),
        "diarization_available": bool(segments)
        and any(segment.speaker is not None for segment in segments),
        "segment_count": len(segments) if segments else 0,
        "confidence": result.confidence if result else None,
        "text": text,
        "wer": None,
    }


def write_report(
    report: dict[str, Any], *, results_dir: Path, provider: str, audio_file: str
) -> Path:
    provider_dir = results_dir / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    output_path = provider_dir / f"{Path(audio_file).stem}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
