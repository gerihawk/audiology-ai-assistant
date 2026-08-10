"""Formato de metadata de un caso del dataset (`metadata.json`) — ver
docs/transcription-benchmark.md §Metadata format.

```json
{
  "id": "consulta_ficticia_01",
  "description": "Consulta básica, ambiente limpio, dos hablantes",
  "language": "es",
  "duration_expected_seconds": 120,
  "number_of_speakers": 2,
  "environment": "quiet_clinic",
  "noise_level": "none",
  "critical_terms": ["hipoacusia", "acúfenos", "audiometría tonal"],
  "negation_cases": [
    {
      "concept": "vertigo",
      "expected": "negated",
      "patterns": {
        "negated": ["no tiene vértigo", "no vértigo", "niega vértigo"],
        "affirmed": ["tiene vértigo", "sí vértigo", "refiere vértigo"]
      }
    }
  ],
  "laterality_cases": [
    {
      "concept": "tinnitus",
      "laterality": "left",
      "patterns": {
        "left": ["oído izquierdo"],
        "right": ["oído derecho"],
        "bilateral": ["ambos oídos", "los dos oídos", "bilateral"]
      }
    }
  ],
  "notes": "Grabado con dos personas distintas para permitir evaluar diarización."
}
```

`negation_cases[].patterns`/`laterality_cases[].patterns` son una
extensión deliberada sobre el ejemplo mínimo del encargo: sin un
fragmento/patrón explícito no hay forma reproducible de comprobar la
hipótesis contra el `concept` abstracto — ver
docs/transcription-benchmark.md §Negaciones/§Lateralidad.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_VALID_ENVIRONMENTS = frozenset(
    {"quiet_clinic", "office_noise", "background_conversation", "street_noise"}
)


class MetadataValidationError(ValueError):
    """El contenido de `metadata.json` no cumple el formato esperado."""


@dataclass(slots=True, frozen=True)
class NegationCase:
    concept: str
    expected: Literal["negated", "affirmed"]
    patterns: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LateralityCase:
    concept: str
    laterality: Literal["left", "right", "bilateral"]
    patterns: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DatasetMetadata:
    id: str
    description: str
    language: str
    number_of_speakers: int
    environment: str
    noise_level: str | None
    duration_expected_seconds: float | None
    critical_terms: list[str]
    negation_cases: list[NegationCase]
    laterality_cases: list[LateralityCase]
    notes: str | None


def metadata_from_dict(data: dict[str, Any]) -> DatasetMetadata:
    try:
        dataset_id = data["id"]
        description = data["description"]
        language = data["language"]
        number_of_speakers = data["number_of_speakers"]
        environment = data["environment"]
    except KeyError as exc:
        raise MetadataValidationError(f"Falta el campo obligatorio: {exc}") from exc

    if environment not in _VALID_ENVIRONMENTS:
        raise MetadataValidationError(
            f"environment='{environment}' no reconocido. Valores válidos: "
            f"{', '.join(sorted(_VALID_ENVIRONMENTS))}."
        )

    negation_cases = [
        NegationCase(concept=c["concept"], expected=c["expected"], patterns=c.get("patterns", {}))
        for c in data.get("negation_cases", [])
    ]
    laterality_cases = [
        LateralityCase(
            concept=c["concept"], laterality=c["laterality"], patterns=c.get("patterns", {})
        )
        for c in data.get("laterality_cases", [])
    ]

    return DatasetMetadata(
        id=dataset_id,
        description=description,
        language=language,
        number_of_speakers=number_of_speakers,
        environment=environment,
        noise_level=data.get("noise_level"),
        duration_expected_seconds=data.get("duration_expected_seconds"),
        critical_terms=data.get("critical_terms", []),
        negation_cases=negation_cases,
        laterality_cases=laterality_cases,
        notes=data.get("notes"),
    )


def load_metadata(path: Path) -> DatasetMetadata:
    data = json.loads(path.read_text(encoding="utf-8"))
    return metadata_from_dict(data)
