"""Formato de `reference.json` — la referencia HUMANA de lo que debería
generar el modelo para un caso, nunca la salida de un LLM (encargo de la
Fase 6.2 §3: "Nunca usar AssemblyAI/Deepgram/OpenAI/Claude/Gemini/ningún
LLM para crear automáticamente la referencia definitiva").

`content` debe cumplir el mismo schema cerrado que valida
`app.ai_pipeline.domain.schemas.validate_content_schema` para el
`artifact_type` del caso — es la MISMA fuente de verdad que usarán el
benchmark, la validación de schema, un futuro `PipelineStep` y producción
en el hito 6.3, nunca un schema propio del benchmark.

Un caso sin `reference.json`, o con `content: null` (plantilla vacía a la
espera de que el profesional la rellene — ver
`generation_dataset/README.md`), carga con `reference=None`: el dataset
sigue siendo listable/inspeccionable, pero
`GenerationBenchmarkRunner` se niega a invocar un modelo real para ese
caso (ver runner.py) — nunca se inventa la referencia para poder avanzar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.schemas import validate_content_schema


class ReferenceValidationError(ValueError):
    """`reference.json` existe, declara contenido, pero no cumple el
    schema cerrado del `artifact_type` — error de autoría, no una
    referencia pendiente."""


@dataclass(slots=True, frozen=True)
class GenerationReference:
    artifact_type: AIArtifactType
    content: dict[str, Any]
    notes: str | None


def reference_from_dict(
    data: dict[str, Any], *, expected_artifact_type: AIArtifactType
) -> GenerationReference | None:
    content = data.get("content")
    if content is None:
        # Plantilla todavía no rellenada por un humano — nunca un error.
        return None

    try:
        artifact_type = AIArtifactType(data["artifact_type"])
    except KeyError as exc:
        raise ReferenceValidationError("Falta el campo obligatorio 'artifact_type'.") from exc

    if artifact_type is not expected_artifact_type:
        raise ReferenceValidationError(
            f"reference.json declara artifact_type='{artifact_type.value}', pero "
            f"input.json declara '{expected_artifact_type.value}'."
        )

    schema_result = validate_content_schema(artifact_type, content)
    if not schema_result.valid:
        raise ReferenceValidationError(
            f"reference.content no cumple el schema de '{artifact_type.value}': "
            + "; ".join(schema_result.errors)
        )

    return GenerationReference(
        artifact_type=artifact_type, content=content, notes=data.get("notes")
    )


def load_reference(
    path: Path, *, expected_artifact_type: AIArtifactType
) -> GenerationReference | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return reference_from_dict(data, expected_artifact_type=expected_artifact_type)
