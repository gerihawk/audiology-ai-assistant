"""WER (Word Error Rate) — ver docs/transcription-benchmark.md §WER.

`WER = (substitutions + deletions + insertions) / reference_word_count`.
Reutiliza `align_words` (metrics/alignment.py) para poder exponer también
la alineación completa, que terminología/lateralidad/diarización
reutilizan en vez de reimplementar su propia comparación de texto.
"""

from __future__ import annotations

from dataclasses import dataclass

from benchmark.metrics.alignment import AlignmentOp, align_words
from benchmark.metrics.text_normalize import normalize_words


@dataclass(slots=True, frozen=True)
class WerResult:
    value: float
    substitutions: int
    deletions: int
    insertions: int
    reference_word_count: int
    alignment: list[AlignmentOp]


def compute_wer(reference_text: str, hypothesis_text: str) -> WerResult:
    ref_words = normalize_words(reference_text)
    hyp_words = normalize_words(hypothesis_text)
    alignment = align_words(ref_words, hyp_words)

    substitutions = sum(1 for op in alignment if op.op == "sub")
    deletions = sum(1 for op in alignment if op.op == "del")
    insertions = sum(1 for op in alignment if op.op == "ins")
    reference_word_count = len(ref_words)

    value = (
        (substitutions + deletions + insertions) / reference_word_count
        if reference_word_count
        else 0.0
    )

    return WerResult(
        value=value,
        substitutions=substitutions,
        deletions=deletions,
        insertions=insertions,
        reference_word_count=reference_word_count,
        alignment=alignment,
    )
