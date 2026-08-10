"""Negation accuracy — ver docs/transcription-benchmark.md §Negaciones.

Deliberadamente sin heurísticas clínicas ni NLP: cada caso declara en
`metadata.json` los fragmentos/patrones explícitos esperados para la
negación y para su opuesto (afirmación). Se busca cuál de los dos
conjuntos de patrones aparece en la hipótesis — reproducible y testeable,
sin intentar "entender" la frase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchmark.dataset_metadata import NegationCase
from benchmark.metrics.text_normalize import normalize_text

NegationResultValue = Literal["pass", "fail", "not_detected"]

_OPPOSITE = {"negated": "affirmed", "affirmed": "negated"}


@dataclass(slots=True, frozen=True)
class NegationCaseResult:
    concept: str
    expected: str
    result: NegationResultValue
    matched_pattern: str | None


@dataclass(slots=True, frozen=True)
class NegationReport:
    passed: int
    failed: int
    details: list[NegationCaseResult]


def _first_match(haystack_padded: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized and f" {normalized} " in haystack_padded:
            return pattern
    return None


def evaluate_negations(hypothesis_text: str, cases: list[NegationCase]) -> NegationReport:
    hyp_padded = f" {normalize_text(hypothesis_text)} "

    details: list[NegationCaseResult] = []
    for case in cases:
        expected_patterns = case.patterns.get(case.expected, [])
        opposite_key = _OPPOSITE[case.expected]
        opposite_patterns = case.patterns.get(opposite_key, [])

        matched_expected = _first_match(hyp_padded, expected_patterns)
        if matched_expected:
            details.append(
                NegationCaseResult(
                    concept=case.concept,
                    expected=case.expected,
                    result="pass",
                    matched_pattern=matched_expected,
                )
            )
            continue

        matched_opposite = _first_match(hyp_padded, opposite_patterns)
        if matched_opposite:
            details.append(
                NegationCaseResult(
                    concept=case.concept,
                    expected=case.expected,
                    result="fail",
                    matched_pattern=matched_opposite,
                )
            )
            continue

        details.append(
            NegationCaseResult(
                concept=case.concept,
                expected=case.expected,
                result="not_detected",
                matched_pattern=None,
            )
        )

    passed = sum(1 for d in details if d.result == "pass")
    failed = sum(1 for d in details if d.result == "fail")
    return NegationReport(passed=passed, failed=failed, details=details)
