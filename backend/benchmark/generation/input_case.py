"""Formato de `input.json` de un caso del benchmark de generación — ver
docs/generation-benchmark.md §Dataset.

```json
{
  "id": "consulta_ficticia_01__summary",
  "language": "es",
  "artifact_type": "summary",
  "session_type": null,
  "transcript": "...",
  "transcript_segments": [
    {"speaker": "audiologist", "start_ms": null, "end_ms": null, "text": "..."}
  ],
  "context": {"summary_text": "..."},
  "prompt_template": {"name": "summary_es_v1"},
  "case_metadata": {"source_transcript_id": "consulta_ficticia_01"}
}
```

`context` son variables adicionales explícitamente permitidas para
`RenderContext` (p. ej. el `summary_text` que `MISSING_INFORMATION`/
`PATIENT_SUMMARY` reciben como dependencia — ver
docs/fase-6-rfc.md §4.3/§4.5) — siempre `dict[str, str]`, nunca
estructuras anidadas, porque `RenderContext.variables` solo acepta str
(ver `app/ai_pipeline/domain/prompt_renderer.py`). `prompt_template` fija
opcionalmente el *nombre* de una plantilla concreta (resuelta vía
`PromptTemplateRepository.get_active_by_name`); si es `null`, el runner
resuelve la plantilla activa por `(artifact_type, language)`. Solo
`name`, nunca una versión histórica concreta: `PromptTemplateRepository`
(Fase 6.0.5) no expone "obtener versión N de una plantilla inactiva" —
el resultado siempre registra el `template_id`/`template_version`
realmente usado (reproducibilidad, ver encargo §18), aunque no se pueda
pedir una versión pasada explícitamente todavía.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType


class InputValidationError(ValueError):
    """El contenido de `input.json` no cumple el formato esperado."""


@dataclass(slots=True, frozen=True)
class TranscriptSegment:
    speaker: str | None
    start_ms: int | None
    end_ms: int | None
    text: str


@dataclass(slots=True, frozen=True)
class PromptTemplateRef:
    name: str


@dataclass(slots=True, frozen=True)
class GenerationInput:
    id: str
    language: str
    artifact_type: AIArtifactType
    session_type: str | None
    transcript: str
    transcript_segments: tuple[TranscriptSegment, ...]
    context: dict[str, str]
    prompt_template: PromptTemplateRef | None
    case_metadata: dict[str, Any]


def input_from_dict(data: dict[str, Any]) -> GenerationInput:
    try:
        case_id = data["id"]
        language = data["language"]
        artifact_type_raw = data["artifact_type"]
        transcript = data["transcript"]
    except KeyError as exc:
        raise InputValidationError(f"Falta el campo obligatorio en input.json: {exc}") from exc

    try:
        artifact_type = AIArtifactType(artifact_type_raw)
    except ValueError as exc:
        raise InputValidationError(
            f"artifact_type='{artifact_type_raw}' no es un AIArtifactType válido."
        ) from exc

    segments = tuple(
        TranscriptSegment(
            speaker=segment.get("speaker"),
            start_ms=segment.get("start_ms"),
            end_ms=segment.get("end_ms"),
            text=segment["text"],
        )
        for segment in data.get("transcript_segments") or []
    )

    context = data.get("context") or {}
    if not all(isinstance(value, str) for value in context.values()):
        raise InputValidationError(
            "Todos los valores de 'context' deben ser str (RenderContext.variables lo exige)."
        )

    prompt_template_raw = data.get("prompt_template")
    prompt_template = (
        PromptTemplateRef(name=prompt_template_raw["name"]) if prompt_template_raw else None
    )

    return GenerationInput(
        id=case_id,
        language=language,
        artifact_type=artifact_type,
        session_type=data.get("session_type"),
        transcript=transcript,
        transcript_segments=segments,
        context=context,
        prompt_template=prompt_template,
        case_metadata=data.get("case_metadata") or {},
    )


def load_input(path: Path) -> GenerationInput:
    data = json.loads(path.read_text(encoding="utf-8"))
    return input_from_dict(data)
