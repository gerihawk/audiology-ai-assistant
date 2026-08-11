"""Secuencia única y explícita de validación de contenido generado
automáticamente antes de poder persistirse como `AIArtifactVersion` — ver
docs/fase-6-rfc.md §5.1 y el encargo de la Fase 6.1, punto 6
("validate → persist", nunca al revés — ver también §11 del encargo).

Orden obligatorio (RFC §5.1, pasos 3 a 7 — los pasos 1/2/8/9 son
responsabilidad de `run_provider_step`/`AIPipelineService`, no de este
módulo):

1. `validate_content_schema` — schema estructural cerrado del
   `artifact_type` (RFC pasos 3 "JSON/schema" + 4 "validación estructural
   específica": los `Mock*Generator` ya devuelven un `dict` de Python, sin
   texto JSON que parsear, así que ambos pasos colapsan en uno).
2. `detect_evasive_response` — resto del paso 3 (metacomentario/negativa).
3. Grounding de cada bloque que declare `source_excerpt` (paso 5) y
   construcción de `source_map` a partir de los extractos ya validados
   (paso 6) — nunca al revés, `source_map` nunca lo aporta el proveedor
   como autoridad (§5.4).
4. `validate_safety` sobre todos los textos terminales (paso 7).

Un artefacto con campos que requieren evidencia y carecen de mapa válido
no puede persistirse como generación exitosa (§5.4): hoy solo
`CLINICAL_FLAGS` declara `source_excerpt`, así que es el único tipo donde
este paso puede fallar — para el resto (`ANAMNESIS` incluida, hasta que el
hito 6.4 le añada `source_excerpt` real) es un no-op determinista.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai_pipeline.domain.content_walk import iter_dict_nodes
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.evasive import detect_evasive_response
from app.ai_pipeline.domain.grounding import verify_excerpt
from app.ai_pipeline.domain.safety import validate_safety
from app.ai_pipeline.domain.schemas import validate_content_schema


@dataclass(slots=True, frozen=True)
class ValidationOutcome:
    ok: bool
    #: `None` si `ok` es `False` — nunca se expone contenido a medio
    #: validar como si fuera utilizable.
    content: dict[str, Any] | None
    source_map: dict[str, Any] | None
    failure_reason: AIGenerationFailureReason | None
    #: Identificadores de regla de seguridad violada, seguros para
    #: auditoría/logging (nunca el texto clínico) — vacío salvo cuando
    #: `failure_reason is SAFETY_POLICY_FAILED`.
    violated_rule_ids: tuple[str, ...] = ()


def validate_generated_content(
    artifact_type: AIArtifactType, content: Any, reference_text: str
) -> ValidationOutcome:
    schema_result = validate_content_schema(artifact_type, content)
    if not schema_result.valid:
        return ValidationOutcome(
            ok=False,
            content=None,
            source_map=None,
            failure_reason=AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED,
        )

    if detect_evasive_response(content):
        return ValidationOutcome(
            ok=False,
            content=None,
            source_map=None,
            failure_reason=AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE,
        )

    source_map, grounding_ok = _build_source_map(content, reference_text)
    if not grounding_ok:
        return ValidationOutcome(
            ok=False,
            content=None,
            source_map=None,
            failure_reason=AIGenerationFailureReason.GROUNDING_FAILED,
        )

    safety_result = validate_safety(content)
    if not safety_result.valid:
        return ValidationOutcome(
            ok=False,
            content=None,
            source_map=None,
            failure_reason=AIGenerationFailureReason.SAFETY_POLICY_FAILED,
            violated_rule_ids=safety_result.rule_ids,
        )

    return ValidationOutcome(ok=True, content=content, source_map=source_map, failure_reason=None)


def _build_source_map(content: Any, reference_text: str) -> tuple[dict[str, Any] | None, bool]:
    source_map: dict[str, Any] = {}
    for path, node in iter_dict_nodes(content):
        if "source_excerpt" not in node:
            continue
        excerpt = node["source_excerpt"]
        if excerpt is None:
            continue  # el campo declara la clave pero no aporta evidencia — nada que verificar.
        if not isinstance(excerpt, str):
            continue  # tipo inválido ya rechazado por el schema; nunca llega aquí en la práctica.

        result = verify_excerpt(excerpt, reference_text)
        if not result.grounded:
            return None, False

        entry: dict[str, Any] = {"field": path, "excerpt": excerpt}
        if result.original_start is not None:
            entry["original_start"] = result.original_start
            entry["original_end"] = result.original_end
        source_map[path] = entry

    return (source_map or None), True
