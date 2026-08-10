"""Construcción y persistencia del informe JSON normalizado de una
ejecución de benchmark — ver docs/transcription-benchmark.md §Benchmark
result schema.

Todas las métricas de `metrics{}` son opcionales y se calculan solo si
hay datos suficientes: `wer`/`terminology` requieren `reference.json`
(fuente de verdad), `negations`/`laterality` requieren `metadata.json`
(patrones declarados), `diarization` siempre reporta lo detectable desde
el resultado del proveedor y añade `reference_speaker_count`/
`attribution_accuracy` si además hay `reference.json`. Un caso del
dataset sin ninguno de los dos ficheros sigue generando un informe válido
con `metrics` en `None`/parcial — nunca un error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.dataset_metadata import DatasetMetadata
from benchmark.metrics.diarization import HypothesisSegment, evaluate_diarization
from benchmark.metrics.laterality import evaluate_laterality
from benchmark.metrics.negation import evaluate_negations
from benchmark.metrics.terminology import evaluate_terminology
from benchmark.metrics.wer import compute_wer
from benchmark.reference import Reference, reference_full_text
from benchmark.runner import BenchmarkOutcome


def build_report(
    outcome: BenchmarkOutcome,
    *,
    estimated_cost_usd: str,
    estimated_cost_source: str,
    pricing_version: str | None,
    pricing_effective_date: str | None,
    reference: Reference | None,
    metadata: DatasetMetadata | None,
) -> dict[str, Any]:
    result = outcome.result
    text = result.text if result else ""
    word_count = len(text.split()) if text else 0
    duration_ms = result.duration_ms if result else None
    segments = result.segments or [] if result else []

    hypothesis_segments = [HypothesisSegment(speaker=s.speaker, text=s.text) for s in segments]

    real_time_factor = (
        outcome.response_time_ms / duration_ms if duration_ms and duration_ms > 0 else None
    )

    metrics_block = _build_metrics_block(
        hypothesis_text=text,
        hypothesis_segments=hypothesis_segments,
        reference=reference,
        metadata=metadata,
        result_available=result is not None,
    )

    has_diarization = bool(segments) and any(s.speaker for s in segments)

    return {
        "provider": outcome.provider,
        "model": result.model_name if result else None,
        "audio_id": outcome.audio_id,
        "audio_duration_ms": duration_ms,
        "processing_time_ms": outcome.response_time_ms,
        "real_time_factor": real_time_factor,
        "estimated_cost_usd": estimated_cost_usd,
        "estimated_cost_source": estimated_cost_source,
        "pricing_version": pricing_version,
        "pricing_effective_date": pricing_effective_date,
        "language": result.language if result else None,
        "succeeded": outcome.succeeded,
        "error": outcome.error,
        "ran_at": outcome.ran_at,
        "transcription": {
            "text": text,
            "word_count": word_count,
            "segments": [
                {
                    "speaker": s.speaker,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "text": s.text,
                }
                for s in segments
            ],
        },
        "metrics": metrics_block,
        "capabilities": {
            "diarization": has_diarization,
            "timestamps": bool(segments),
            "confidence": bool(result and result.confidence is not None),
        },
    }


def _build_metrics_block(
    *,
    hypothesis_text: str,
    hypothesis_segments: list[HypothesisSegment],
    reference: Reference | None,
    metadata: DatasetMetadata | None,
    result_available: bool,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "wer": None,
        "terminology": None,
        "negations": None,
        "laterality": None,
        "diarization": None,
    }
    if not result_available:
        return metrics

    if reference is not None:
        reference_text = reference_full_text(reference)
        wer_result = compute_wer(reference_text, hypothesis_text)
        metrics["wer"] = {
            "value": wer_result.value,
            "substitutions": wer_result.substitutions,
            "deletions": wer_result.deletions,
            "insertions": wer_result.insertions,
            "reference_word_count": wer_result.reference_word_count,
        }

        if metadata is not None and metadata.critical_terms:
            terminology_result = evaluate_terminology(
                reference_text, hypothesis_text, metadata.critical_terms
            )
            metrics["terminology"] = {
                "accuracy": terminology_result.accuracy,
                "details": [
                    {
                        "term": d.term,
                        "present_in_reference": d.present_in_reference,
                        "status": d.status,
                    }
                    for d in terminology_result.details
                ],
            }

        diarization_result = evaluate_diarization(reference, hypothesis_segments)
        metrics["diarization"] = {
            "reference_speaker_count": diarization_result.reference_speaker_count,
            "detected_speaker_count": diarization_result.detected_speaker_count,
            "speaker_count_match": diarization_result.speaker_count_match,
            "attribution_accuracy": diarization_result.attribution_accuracy,
            "number_of_reference_segments": diarization_result.number_of_reference_segments,
            "number_of_provider_segments": diarization_result.number_of_provider_segments,
        }
    else:
        # Sin reference.json: se sigue reportando lo detectable del propio
        # resultado del proveedor (conteo de hablantes/segmentos), sin
        # comparación contra una fuente de verdad.
        detected_speakers = {s.speaker for s in hypothesis_segments if s.speaker}
        metrics["diarization"] = {
            "reference_speaker_count": None,
            "detected_speaker_count": len(detected_speakers),
            "speaker_count_match": None,
            "attribution_accuracy": None,
            "number_of_reference_segments": None,
            "number_of_provider_segments": len(hypothesis_segments),
        }

    if metadata is not None:
        if metadata.negation_cases:
            negation_result = evaluate_negations(hypothesis_text, metadata.negation_cases)
            metrics["negations"] = {
                "passed": negation_result.passed,
                "failed": negation_result.failed,
                "details": [
                    {
                        "concept": d.concept,
                        "expected": d.expected,
                        "result": d.result,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in negation_result.details
                ],
            }
        if metadata.laterality_cases:
            laterality_result = evaluate_laterality(hypothesis_text, metadata.laterality_cases)
            metrics["laterality"] = {
                "passed": laterality_result.passed,
                "failed": laterality_result.failed,
                "details": [
                    {
                        "concept": d.concept,
                        "expected": d.expected,
                        "result": d.result,
                        "matched_pattern": d.matched_pattern,
                        "matched_laterality": d.matched_laterality,
                    }
                    for d in laterality_result.details
                ],
            }

    return metrics


def write_report(
    report: dict[str, Any], *, results_dir: Path, provider: str, audio_id: str
) -> Path:
    provider_dir = results_dir / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    output_path = provider_dir / f"{audio_id}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
