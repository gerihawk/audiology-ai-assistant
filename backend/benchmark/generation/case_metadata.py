"""Formato de `metadata.json` de un caso del benchmark de generación —
qué invariantes clínicas importan para este caso concreto (encargo de la
Fase 6.2 §4: "Cada caso declara solo las invariantes relevantes", nunca
todos los campos indiscriminadamente).

```json
{
  "id": "consulta_ficticia_01__summary",
  "description": "...",
  "artifact_type": "summary",
  "required_facts": [
    {
      "description": "pérdida auditiva bilateral, más marcada en oído izquierdo",
      "patterns": ["oído izquierdo", "los dos oídos"]
    }
  ],
  "forbidden_facts": [
    {"description": "vértigo (negado explícitamente)", "patterns": ["vértigo"]}
  ],
  "critical_terms": ["hipoacusia", "acúfenos"],
  "negation_cases": [...],
  "laterality_cases": [...],
  "numeric_cases": [
    {
      "concept": "duracion_sintomas",
      "expected_patterns": ["ocho o nueve meses"],
      "incorrect_patterns": ["dos meses", "un año"]
    }
  ],
  "expected_missing_topics": [
    {"description": "grado exacto de pérdida auditiva", "patterns": ["grado"]}
  ],
  "max_length": null,
  "notes": "..."
}
```

`negation_cases`/`laterality_cases` reutilizan tal cual `NegationCase`/
`LateralityCase` de `benchmark.dataset_metadata` (mismo formato, mismo
motor determinista de `benchmark/metrics/negation.py`/`laterality.py`) —
nunca se reimplementan (encargo Fase 6.2 §10, "no dupliques").
`expected_missing_topics` solo aplica a `artifact_type=missing_information`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.dataset_metadata import LateralityCase, NegationCase


class CaseMetadataValidationError(ValueError):
    """El contenido de `metadata.json` no cumple el formato esperado."""


@dataclass(slots=True, frozen=True)
class FactCase:
    description: str
    patterns: list[str]


@dataclass(slots=True, frozen=True)
class NumericCase:
    concept: str
    expected_patterns: list[str]
    incorrect_patterns: list[str]


@dataclass(slots=True, frozen=True)
class GenerationCaseMetadata:
    id: str
    description: str
    artifact_type: str
    required_facts: list[FactCase]
    forbidden_facts: list[FactCase]
    critical_terms: list[str]
    negation_cases: list[NegationCase]
    laterality_cases: list[LateralityCase]
    numeric_cases: list[NumericCase]
    expected_missing_topics: list[FactCase]
    max_length: int | None
    notes: str | None


def _fact_cases(raw: list[dict[str, Any]]) -> list[FactCase]:
    return [FactCase(description=c["description"], patterns=c.get("patterns", [])) for c in raw]


def metadata_from_dict(data: dict[str, Any]) -> GenerationCaseMetadata:
    try:
        case_id = data["id"]
        description = data["description"]
        artifact_type = data["artifact_type"]
    except KeyError as exc:
        raise CaseMetadataValidationError(f"Falta el campo obligatorio: {exc}") from exc

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
    numeric_cases = [
        NumericCase(
            concept=c["concept"],
            expected_patterns=c.get("expected_patterns", []),
            incorrect_patterns=c.get("incorrect_patterns", []),
        )
        for c in data.get("numeric_cases", [])
    ]

    return GenerationCaseMetadata(
        id=case_id,
        description=description,
        artifact_type=artifact_type,
        required_facts=_fact_cases(data.get("required_facts", [])),
        forbidden_facts=_fact_cases(data.get("forbidden_facts", [])),
        critical_terms=data.get("critical_terms", []),
        negation_cases=negation_cases,
        laterality_cases=laterality_cases,
        numeric_cases=numeric_cases,
        expected_missing_topics=_fact_cases(data.get("expected_missing_topics", [])),
        max_length=data.get("max_length"),
        notes=data.get("notes"),
    )


def load_case_metadata(path: Path) -> GenerationCaseMetadata:
    data = json.loads(path.read_text(encoding="utf-8"))
    return metadata_from_dict(data)
