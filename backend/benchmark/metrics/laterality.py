"""Laterality accuracy — ver docs/transcription-benchmark.md §Lateralidad.

Mismo principio que negation.py (metrics/negation.py): sin NLP clínico,
comparación textual configurada mediante patrones explícitos por
lateralidad (`left`/`right`/`bilateral`) declarados en `metadata.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchmark.dataset_metadata import LateralityCase
from benchmark.metrics.text_normalize import normalize_text

LateralityResultValue = Literal["pass", "fail", "not_detected"]

_LATERALITIES = ("left", "right", "bilateral")


@dataclass(slots=True, frozen=True)
class LateralityCaseResult:
    concept: str
    expected: str
    result: LateralityResultValue
    matched_pattern: str | None
    matched_laterality: str | None


@dataclass(slots=True, frozen=True)
class LateralityReport:
    passed: int
    failed: int
    details: list[LateralityCaseResult]


def _first_match(haystack_padded: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized and f" {normalized} " in haystack_padded:
            return pattern
    return None


def evaluate_laterality(hypothesis_text: str, cases: list[LateralityCase]) -> LateralityReport:
    hyp_padded = f" {normalize_text(hypothesis_text)} "

    details: list[LateralityCaseResult] = []
    for case in cases:
        expected_patterns = case.patterns.get(case.laterality, [])
        matched_expected = _first_match(hyp_padded, expected_patterns)
        if matched_expected:
            details.append(
                LateralityCaseResult(
                    concept=case.concept,
                    expected=case.laterality,
                    result="pass",
                    matched_pattern=matched_expected,
                    matched_laterality=case.laterality,
                )
            )
            continue

        matched_wrong: tuple[str, str] | None = None
        for other in _LATERALITIES:
            if other == case.laterality:
                continue
            match = _first_match(hyp_padded, case.patterns.get(other, []))
            if match:
                matched_wrong = (other, match)
                break

        if matched_wrong:
            other_laterality, matched_pattern = matched_wrong
            details.append(
                LateralityCaseResult(
                    concept=case.concept,
                    expected=case.laterality,
                    result="fail",
                    matched_pattern=matched_pattern,
                    matched_laterality=other_laterality,
                )
            )
            continue

        details.append(
            LateralityCaseResult(
                concept=case.concept,
                expected=case.laterality,
                result="not_detected",
                matched_pattern=None,
                matched_laterality=None,
            )
        )

    passed = sum(1 for d in details if d.result == "pass")
    failed = sum(1 for d in details if d.result == "fail")
    return LateralityReport(passed=passed, failed=failed, details=details)
