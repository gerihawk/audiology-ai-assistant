"""Métricas deterministas de generación — encargo de la Fase 6.2 §5.

Reutiliza directamente lo que ya existe en vez de duplicarlo:

- **Schema validity / grounding / safety**: `validate_generated_content`
  (`app.ai_pipeline.domain.validation_pipeline`) — invocado por
  `runner.py`, nunca reimplementado aquí.
- **Terminología / negaciones / lateralidad**: los mismos evaluadores
  deterministas del benchmark de transcripción
  (`benchmark.metrics.terminology`/`negation`/`laterality`), reutilizados
  tal cual sobre el texto aplanado del contenido generado — mismo motor,
  cero reimplementación.

Lo único nuevo aquí es lo que no existía: preservación de hechos
obligatorios, alucinación de hechos prohibidos, exactitud numérica (mismo
principio de patrones explícitos que negación/lateralidad, nunca NLP) y
completitud de `missing_information`. Sin heurísticas de comprensión
semántica en ningún caso — solo lo declarado explícitamente en
`metadata.json` (encargo §5, "no intentes resolver hallucination
semántica general con heurísticas frágiles")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.ai_pipeline.domain.content_walk import iter_dict_nodes, iter_string_leaves
from app.core.text_normalize import normalize_text
from benchmark.generation.case_metadata import FactCase, NumericCase


def flatten_content_text(content: Any) -> str:
    """Concatena todos los strings hoja de `content` — misma primitiva
    genérica que ya usan `SafetyValidator`/`detect_evasive_response`
    (`content_walk.iter_string_leaves`), nunca un recorrido nuevo."""
    return " ".join(text for _, text in iter_string_leaves(content))


def flatten_missing_information_topics(content: Any) -> str:
    """Concatena únicamente `items[].topic` de un `content` de
    `MISSING_INFORMATION` — nunca `suggested_question`.

    `topic` es lo único que declara explícitamente qué gap afirma el
    modelo; `suggested_question` es redacción auxiliar que puede
    mencionar legítimamente conceptos ya cubiertos al formular una
    pregunta de seguimiento más concreta (encargo Fase 6.2, diagnóstico
    post-mortem 2026-08-12: los falsos positivos de `forbidden_facts`
    venían de comprobar todo el output aplanado, incluida la pregunta).
    Uso exclusivo de `evaluate_forbidden_facts` en `runner.py` para este
    artifact_type — `evaluate_missing_information_completeness` sigue
    usando `topic + suggested_question` deliberadamente (pregunta
    distinta: si el modelo identificó el gap, no cómo tituló el topic).

    Mismo manejo defensivo de estructuras inválidas que
    `evaluate_missing_information_completeness` — nunca lanza, nunca
    asume forma."""
    items = content.get("items") if isinstance(content, dict) else None
    topics = (item.get("topic") for item in (items or []) if isinstance(item, dict))
    return " ".join(topic for topic in topics if isinstance(topic, str))


def _matches_any(haystack_padded: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized and f" {normalized} " in haystack_padded:
            return pattern
    return None


def _padded(text: str) -> str:
    return f" {normalize_text(text)} "


# --- Fact preservation / hallucination -----------------------------------


@dataclass(slots=True, frozen=True)
class FactCheckDetail:
    description: str
    matched: bool
    matched_pattern: str | None


@dataclass(slots=True, frozen=True)
class FactPreservationReport:
    present: int
    missing: int
    details: list[FactCheckDetail]


@dataclass(slots=True, frozen=True)
class HallucinationReport:
    forbidden_found: int
    details: list[FactCheckDetail]


def evaluate_required_facts(generated_text: str, cases: list[FactCase]) -> FactPreservationReport:
    haystack = _padded(generated_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in cases
    ]
    present = sum(1 for d in details if d.matched)
    return FactPreservationReport(present=present, missing=len(details) - present, details=details)


def evaluate_forbidden_facts(generated_text: str, cases: list[FactCase]) -> HallucinationReport:
    haystack = _padded(generated_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in cases
    ]
    forbidden_found = sum(1 for d in details if d.matched)
    return HallucinationReport(forbidden_found=forbidden_found, details=details)


# --- Numeric accuracy ------------------------------------------------------

NumericResultValue = Literal["pass", "fail", "not_detected"]


@dataclass(slots=True, frozen=True)
class NumericCaseResult:
    concept: str
    result: NumericResultValue
    matched_pattern: str | None


@dataclass(slots=True, frozen=True)
class NumericReport:
    passed: int
    failed: int
    details: list[NumericCaseResult]


def evaluate_numeric(generated_text: str, cases: list[NumericCase]) -> NumericReport:
    haystack = _padded(generated_text)
    details: list[NumericCaseResult] = []
    for case in cases:
        matched_expected = _matches_any(haystack, case.expected_patterns)
        if matched_expected:
            details.append(
                NumericCaseResult(
                    concept=case.concept, result="pass", matched_pattern=matched_expected
                )
            )
            continue
        matched_incorrect = _matches_any(haystack, case.incorrect_patterns)
        if matched_incorrect:
            details.append(
                NumericCaseResult(
                    concept=case.concept, result="fail", matched_pattern=matched_incorrect
                )
            )
            continue
        details.append(
            NumericCaseResult(concept=case.concept, result="not_detected", matched_pattern=None)
        )

    passed = sum(1 for d in details if d.result == "pass")
    failed = sum(1 for d in details if d.result == "fail")
    return NumericReport(passed=passed, failed=failed, details=details)


# --- Missing information completeness --------------------------------------


@dataclass(slots=True, frozen=True)
class MissingInformationCompletenessReport:
    expected_present: int
    expected_missing: int
    details: list[FactCheckDetail]


def evaluate_missing_information_completeness(
    content: dict[str, Any], expected_topics: list[FactCase]
) -> MissingInformationCompletenessReport:
    items = content.get("items") if isinstance(content, dict) else None
    items_text = " ".join(
        f"{item.get('topic', '')} {item.get('suggested_question', '')}"
        for item in (items or [])
        if isinstance(item, dict)
    )
    haystack = _padded(items_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in expected_topics
    ]
    present = sum(1 for d in details if d.matched)
    return MissingInformationCompletenessReport(
        expected_present=present, expected_missing=len(details) - present, details=details
    )


# --- Required evidence coverage --------------------------------------------


@dataclass(slots=True, frozen=True)
class EvidenceCoverageReport:
    fields_declaring_evidence: int
    fields_with_valid_evidence: int

    @property
    def coverage(self) -> float:
        return self.fields_with_valid_evidence / self.fields_declaring_evidence


def evaluate_evidence_coverage(
    content: Any, source_map: dict[str, Any] | None
) -> EvidenceCoverageReport | None:
    """`None` si el contenido no declara ningún `source_excerpt` — hoy es
    siempre el caso para `SUMMARY`/`MISSING_INFORMATION`/`PATIENT_SUMMARY`
    (ninguno de los tres tiene ese campo en su schema cerrado, ver
    `app/ai_pipeline/domain/schemas.py`), así que este metric queda
    deliberadamente `null` en el alcance del hito 6.2 — se activará solo
    cuando un `artifact_type` con `source_excerpt` real entre en el
    benchmark (p. ej. `SESSION_NOTES`, hito 6.4)."""
    declared = sum(
        1 for _, node in iter_dict_nodes(content) if node.get("source_excerpt") is not None
    )
    if declared == 0:
        return None
    valid = len(source_map or {})
    return EvidenceCoverageReport(
        fields_declaring_evidence=declared, fields_with_valid_evidence=valid
    )
