"""Speaker / diarization metrics — ver docs/transcription-benchmark.md
§Diarización.

Deliberadamente sin DER (Diarization Error Rate) académico completo: una
métrica interpretable y testeable basada en conteo de hablantes y, si hay
referencia con speakers, una atribución básica por mayoría de voto sobre
la alineación de palabras (reutiliza `align_words`, igual que WER) — sin
usar timestamps (opcionales en la referencia, no siempre disponibles).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from benchmark.metrics.alignment import align_words
from benchmark.metrics.text_normalize import normalize_words
from benchmark.reference import Reference, reference_words_with_speaker


@dataclass(slots=True, frozen=True)
class HypothesisSegment:
    speaker: str | None
    text: str


@dataclass(slots=True, frozen=True)
class DiarizationReport:
    reference_speaker_count: int
    detected_speaker_count: int
    speaker_count_match: bool
    number_of_reference_segments: int
    number_of_provider_segments: int
    attribution_accuracy: float | None


def _hypothesis_words_with_speaker(segments: list[HypothesisSegment]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for segment in segments:
        if not segment.speaker:
            continue
        for word in normalize_words(segment.text):
            pairs.append((word, segment.speaker))
    return pairs


def _attribution_accuracy(
    reference: Reference, hypothesis_segments: list[HypothesisSegment]
) -> float | None:
    if not reference.speakers or not hypothesis_segments:
        return None

    ref_pairs = reference_words_with_speaker(reference)
    hyp_pairs = _hypothesis_words_with_speaker(hypothesis_segments)
    if not ref_pairs or not hyp_pairs:
        return None

    ref_words = [word for word, _ in ref_pairs]
    hyp_words = [word for word, _ in hyp_pairs]
    alignment = align_words(ref_words, hyp_words)

    matched = [
        (op.ref_index, op.hyp_index)
        for op in alignment
        if op.op in ("match", "sub") and op.ref_index is not None and op.hyp_index is not None
    ]
    if not matched:
        return None

    # Mapea cada label de proveedor al speaker de referencia con el que
    # más veces coincide (voto mayoritario) — evita depender de que el
    # proveedor use los mismos IDs que la referencia.
    label_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for ref_index, hyp_index in matched:
        ref_speaker = ref_pairs[ref_index][1]
        hyp_label = hyp_pairs[hyp_index][1]
        label_votes[hyp_label][ref_speaker] += 1
    label_to_reference_speaker = {
        label: votes.most_common(1)[0][0] for label, votes in label_votes.items()
    }

    correct = sum(
        1
        for ref_index, hyp_index in matched
        if label_to_reference_speaker.get(hyp_pairs[hyp_index][1]) == ref_pairs[ref_index][1]
    )
    return correct / len(matched)


def evaluate_diarization(
    reference: Reference, hypothesis_segments: list[HypothesisSegment]
) -> DiarizationReport:
    reference_speaker_count = len(reference.speakers)
    detected_speakers = {s.speaker for s in hypothesis_segments if s.speaker}
    detected_speaker_count = len(detected_speakers)

    return DiarizationReport(
        reference_speaker_count=reference_speaker_count,
        detected_speaker_count=detected_speaker_count,
        speaker_count_match=(reference_speaker_count == detected_speaker_count),
        number_of_reference_segments=len(reference.segments),
        number_of_provider_segments=len(hypothesis_segments),
        attribution_accuracy=_attribution_accuracy(reference, hypothesis_segments),
    )
