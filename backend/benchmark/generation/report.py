"""Resultado normalizado y persistencia de una ejecución del benchmark de
generación — encargo de la Fase 6.2 §15/§19.

Nunca incluye API key, cabeceras de autorización ni secretos. Nunca
incluye el prompt completo (encargo §15) — solo metadata de plantilla
(`template_id`/`template_version`); el contenido de la transcripción
tampoco se repite en el resultado, solo el `output` generado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from benchmark.generation.pricing import estimate_cost
from benchmark.generation.runner import GenerationBenchmarkOutcome


def _grounding_valid(outcome: GenerationBenchmarkOutcome) -> bool | None:
    if outcome.validation.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED:
        return False
    if outcome.metrics.evidence_coverage is not None:
        return True
    return None


def _metrics_block(outcome: GenerationBenchmarkOutcome) -> dict[str, Any]:
    metrics = outcome.metrics
    return {
        "fact_preservation": (
            None
            if metrics.required_facts is None
            else {
                "present": metrics.required_facts.present,
                "missing": metrics.required_facts.missing,
                "details": [
                    {
                        "description": d.description,
                        "matched": d.matched,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in metrics.required_facts.details
                ],
            }
        ),
        "hallucination": (
            None
            if metrics.hallucination is None
            else {
                "forbidden_found": metrics.hallucination.forbidden_found,
                "details": [
                    {
                        "description": d.description,
                        "matched": d.matched,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in metrics.hallucination.details
                ],
            }
        ),
        "negation": (
            None
            if metrics.negations is None
            else {
                "passed": metrics.negations.passed,
                "failed": metrics.negations.failed,
                "details": [
                    {
                        "concept": d.concept,
                        "expected": d.expected,
                        "result": d.result,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in metrics.negations.details
                ],
            }
        ),
        "laterality": (
            None
            if metrics.laterality is None
            else {
                "passed": metrics.laterality.passed,
                "failed": metrics.laterality.failed,
                "details": [
                    {
                        "concept": d.concept,
                        "expected": d.expected,
                        "result": d.result,
                        "matched_pattern": d.matched_pattern,
                        "matched_laterality": d.matched_laterality,
                    }
                    for d in metrics.laterality.details
                ],
            }
        ),
        "numeric_accuracy": (
            None
            if metrics.numeric is None
            else {
                "passed": metrics.numeric.passed,
                "failed": metrics.numeric.failed,
                "details": [
                    {"concept": d.concept, "result": d.result, "matched_pattern": d.matched_pattern}
                    for d in metrics.numeric.details
                ],
            }
        ),
        "terminology": (
            None
            if metrics.terminology is None
            else {
                "accuracy": metrics.terminology.accuracy,
                "details": [
                    {
                        "term": d.term,
                        "present_in_reference": d.present_in_reference,
                        "status": d.status,
                    }
                    for d in metrics.terminology.details
                ],
            }
        ),
        "missing_information_completeness": (
            None
            if metrics.missing_information_completeness is None
            else {
                "expected_present": metrics.missing_information_completeness.expected_present,
                "expected_missing": metrics.missing_information_completeness.expected_missing,
                "details": [
                    {
                        "description": d.description,
                        "matched": d.matched,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in metrics.missing_information_completeness.details
                ],
            }
        ),
        "evidence_coverage": (
            None
            if metrics.evidence_coverage is None
            else {
                "fields_declaring_evidence": metrics.evidence_coverage.fields_declaring_evidence,
                "fields_with_valid_evidence": metrics.evidence_coverage.fields_with_valid_evidence,
                "coverage": metrics.evidence_coverage.coverage,
            }
        ),
        "missing_topic_false_positives": (
            None
            if metrics.missing_topic_false_positives is None
            else {
                "forbidden_found": metrics.missing_topic_false_positives.forbidden_found,
                "details": [
                    {
                        "description": d.description,
                        "matched": d.matched,
                        "matched_pattern": d.matched_pattern,
                    }
                    for d in metrics.missing_topic_false_positives.details
                ],
            }
        ),
    }


def build_result(outcome: GenerationBenchmarkOutcome, *, model_profile: str) -> dict[str, Any]:
    llm = outcome.llm_response
    cost = estimate_cost(
        model=outcome.model,
        input_tokens=llm.input_tokens if llm else None,
        output_tokens=llm.output_tokens if llm else None,
        provider_reported_cost_usd=llm.provider_reported_cost_usd if llm else None,
    )

    return {
        "case_id": outcome.case_id,
        "artifact_type": outcome.artifact_type.value,
        "model_profile": model_profile,
        "provider": "openrouter",
        "model": outcome.model,
        "prompt": {
            "template_id": str(outcome.prompt_template_id),
            "template_version": outcome.prompt_template_version,
        },
        "execution": {
            "ran_at": outcome.ran_at,
            "latency_ms": outcome.latency_ms,
            "attempts": outcome.attempts,
            "input_tokens": llm.input_tokens if llm else None,
            "output_tokens": llm.output_tokens if llm else None,
            "estimated_cost_usd": None if cost.amount_usd is None else str(cost.amount_usd),
            "cost_source": cost.source.value,
            "pricing_version": cost.pricing_version,
            "pricing_effective_date": cost.pricing_effective_date,
            "success": outcome.succeeded,
            "failure_reason": (
                outcome.validation.failure_reason.value
                if outcome.validation.failure_reason
                else None
            ),
            "transport_error": outcome.transport_error,
        },
        "validation": {
            "schema_valid": outcome.validation.failure_reason
            != AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED,
            "safety_valid": outcome.validation.failure_reason
            != AIGenerationFailureReason.SAFETY_POLICY_FAILED,
            "grounding_valid": _grounding_valid(outcome),
        },
        "gates": {
            "safety_gate": outcome.gates.safety_gate,
            "hallucination_gate": outcome.gates.hallucination_gate,
            "schema_gate": outcome.gates.schema_gate,
            "negation_laterality_gate": outcome.gates.negation_laterality_gate,
            "passed_all": outcome.gates.passed_all,
            "blocking_gate": outcome.gates.blocking_gate,
        },
        "metrics": _metrics_block(outcome),
        "findings": [
            {"severity": f.severity, "category": f.category, "description": f.description}
            for f in outcome.findings
        ],
        "output": outcome.validation.content,
    }


def write_result(
    result: dict[str, Any], *, results_dir: Path, model_profile: str, case_id: str
) -> Path:
    profile_dir = results_dir / model_profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    output_path = profile_dir / f"{case_id}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
