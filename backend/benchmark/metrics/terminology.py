"""Terminology Error Rate — ver docs/transcription-benchmark.md §Terminología.

Deliberadamente basado en comparación de subcadenas normalizadas, no en
alineación palabra a palabra ni NLP: soporta términos multi-palabra
("audiometría tonal", "vía aérea") sin necesitar resolver su posición
exacta en la alineación de WER.

`substituted` vs. `omitted` (heurística explícita, no NLP): para un
término de más de una palabra, si ALGUNA pero no TODAS sus palabras
aparecen en la hipótesis, se interpreta como "sustituido" (se dijo algo
relacionado pero no la expresión correcta); si NINGUNA aparece, como
"omitido". Un término de una sola palabra solo puede ser
`recognized`/`omitted` — no hay señal de solapamiento parcial posible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchmark.metrics.text_normalize import normalize_text

TermStatus = Literal["recognized", "omitted", "substituted", "not_in_reference"]


@dataclass(slots=True, frozen=True)
class TerminologyTermResult:
    term: str
    present_in_reference: bool
    status: TermStatus


@dataclass(slots=True, frozen=True)
class TerminologyReport:
    accuracy: float | None
    details: list[TerminologyTermResult]


def _contains(haystack_padded: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in haystack_padded


def evaluate_terminology(
    reference_text: str, hypothesis_text: str, terms: list[str]
) -> TerminologyReport:
    ref_padded = f" {normalize_text(reference_text)} "
    hyp_padded = f" {normalize_text(hypothesis_text)} "

    details: list[TerminologyTermResult] = []
    for term in terms:
        term_norm = normalize_text(term)
        if not term_norm:
            continue

        if not _contains(ref_padded, term_norm):
            details.append(
                TerminologyTermResult(
                    term=term, present_in_reference=False, status="not_in_reference"
                )
            )
            continue

        if _contains(hyp_padded, term_norm):
            status: TermStatus = "recognized"
        else:
            term_words = term_norm.split(" ")
            has_partial_overlap = any(_contains(hyp_padded, word) for word in term_words)
            status = "substituted" if (len(term_words) > 1 and has_partial_overlap) else "omitted"

        details.append(TerminologyTermResult(term=term, present_in_reference=True, status=status))

    applicable = [d for d in details if d.status != "not_in_reference"]
    accuracy = (
        sum(1 for d in applicable if d.status == "recognized") / len(applicable)
        if applicable
        else None
    )
    return TerminologyReport(accuracy=accuracy, details=details)
