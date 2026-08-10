"""Formato de referencia manual (`reference.json`) — fuente de verdad para
evaluación. Ver docs/transcription-benchmark.md §Reference format.

```json
{
  "language": "es",
  "speakers": [
    {"id": "audiologist", "label": "Audioprotesista"},
    {"id": "patient", "label": "Paciente"}
  ],
  "segments": [
    {"speaker": "audiologist", "start_ms": null, "end_ms": null, "text": "..."}
  ]
}
```

Los timestamps (`start_ms`/`end_ms`) son opcionales — `null` si no se han
medido a mano. `speaker` en cada segmento debe ser uno de los `id`
declarados en `speakers`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReferenceValidationError(ValueError):
    """El contenido de `reference.json` no cumple el formato esperado."""


@dataclass(slots=True, frozen=True)
class ReferenceSpeaker:
    id: str
    label: str


@dataclass(slots=True, frozen=True)
class ReferenceSegment:
    speaker: str
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(slots=True, frozen=True)
class Reference:
    language: str
    speakers: list[ReferenceSpeaker]
    segments: list[ReferenceSegment]


def reference_from_dict(data: dict[str, Any]) -> Reference:
    try:
        language = data["language"]
        speakers_raw = data["speakers"]
        segments_raw = data["segments"]
    except KeyError as exc:
        raise ReferenceValidationError(f"Falta el campo obligatorio: {exc}") from exc

    speakers = [ReferenceSpeaker(id=s["id"], label=s["label"]) for s in speakers_raw]
    speaker_ids = {s.id for s in speakers}

    segments: list[ReferenceSegment] = []
    for index, raw in enumerate(segments_raw):
        speaker = raw.get("speaker")
        if speaker not in speaker_ids:
            raise ReferenceValidationError(
                f"segments[{index}].speaker='{speaker}' no está declarado en 'speakers' "
                f"({sorted(speaker_ids)})."
            )
        text = raw.get("text", "")
        segments.append(
            ReferenceSegment(
                speaker=speaker,
                text=text,
                start_ms=raw.get("start_ms"),
                end_ms=raw.get("end_ms"),
            )
        )

    return Reference(language=language, speakers=speakers, segments=segments)


def load_reference(path: Path) -> Reference:
    data = json.loads(path.read_text(encoding="utf-8"))
    return reference_from_dict(data)


def reference_full_text(reference: Reference) -> str:
    """Concatena el texto de todos los segmentos en orden — la
    "transcripción de referencia completa" contra la que se calcula WER."""
    return " ".join(segment.text for segment in reference.segments if segment.text)


def reference_words_with_speaker(reference: Reference) -> list[tuple[str, str]]:
    """Expande cada segmento en `(palabra_normalizada, speaker_id)` — usado
    por la métrica de atribución de hablante (metrics/diarization.py)."""
    from benchmark.metrics.text_normalize import normalize_words

    pairs: list[tuple[str, str]] = []
    for segment in reference.segments:
        for word in normalize_words(segment.text):
            pairs.append((word, segment.speaker))
    return pairs
