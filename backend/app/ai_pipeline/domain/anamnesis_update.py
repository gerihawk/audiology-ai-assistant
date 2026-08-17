"""Primitivas de dominio puras para la actualización longitudinal de
ANAMNESIS — Hito 6.5.1 (RFC técnico de 6.5, decisiones cerradas §1-§12).

Sin BD, sin HTTP, sin proveedor real: dado un baseline aprobado (ya
resuelto por `patient_context.py`) y una lista de cambios YA PROPUESTOS
por un generador (6.5.2+, fuera de este módulo), estas funciones:

1. validan que cada cambio sea compatible con su `previous_status`/
   `reason` declarados (`validate_update_batch`) — nunca interpretan
   lenguaje natural, solo comprueban coherencia estructural/lógica de un
   diff ya producido;
2. verifican el grounding de los campos MODIFICADOS exclusivamente
   contra el transcript de la sesión ACTUAL (`verify_update_grounding`)
   — reutiliza `verify_excerpt()` campo a campo, nunca pasa el documento
   completo por `_build_source_map()`/`validate_generated_content()`
   (revalidarían también los campos carried-forward del baseline contra
   un transcript al que no pertenecen — hallazgo de la auditoría de 6.5,
   §9/§19: eso produce `grounding_failed` en falso sobre evidencia
   histórica ya válida);
3. materializan el documento ANAMNESIS final (`materialize_anamnesis`),
   copiando el baseline sin mutarlo y aplicando solo los campos
   cambiados, validado contra el mismo `validate_content_schema` que ya
   usa el resto del pipeline.

El `source_map` resultante de una propuesta de actualización representa
ÚNICAMENTE la evidencia nueva verificada en este update — nunca los 20
campos del documento, nunca proveniencia reconstruida de sesiones
pasadas (RFC técnico de 6.5, Decisión 1).

`AnamnesisUpdateReason`/`AnamnesisFieldUpdate` (Hito 6.5.2): reubicados a
`app.integrations.domain.anamnesis_update_generator` — son vocabulario de
"lo que produce un generator" (mismo criterio que
`AnamnesisFieldValue`/`MissingInfoItem`), no de este módulo de validación
pura; `integrations/domain/` nunca puede importar de `ai_pipeline/`, y el
nuevo `AnamnesisUpdateGenerator` (Protocol) vive en `integrations/domain/`
y necesita este DTO. Reexportados aquí sin cambios de forma ni de
comportamiento para que ningún call site de 6.5.1 se rompa.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.grounding import verify_excerpt
from app.ai_pipeline.domain.schemas import validate_content_schema
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS, AnamnesisFieldStatus
from app.integrations.domain.anamnesis_update_generator import (
    AnamnesisFieldUpdate,
    AnamnesisUpdateReason,
)

__all__ = [
    "AnamnesisFieldUpdate",
    "AnamnesisUpdateReason",
    "InvalidAnamnesisUpdateError",
    "AnamnesisUpdateGroundingResult",
    "validate_update_batch",
    "verify_update_grounding",
    "materialize_anamnesis",
    "changed_field_names",
    "reason_for_previous_status",
]

#: Único origen de verdad de qué `reason` puede originar un cambio real
#: sobre un campo, según su `previous_status` — RFC técnico de 6.5, §5 del
#: encargo de 6.5.1. Cualquier combinación ausente de este mapa es
#: inválida. No se añade una tercera categoría de motivo ("enrichment"):
#: deliberadamente fuera de alcance (ver auditoría de 6.5, §6).
_ALLOWED_REASONS_BY_PREVIOUS_STATUS: dict[
    AnamnesisFieldStatus, frozenset[AnamnesisUpdateReason]
] = {
    AnamnesisFieldStatus.NO_PREGUNTADO: frozenset({AnamnesisUpdateReason.FILLS_GAP}),
    AnamnesisFieldStatus.NO_DETERMINADO: frozenset({AnamnesisUpdateReason.FILLS_GAP}),
    AnamnesisFieldStatus.INFORMADO: frozenset({AnamnesisUpdateReason.EXPLICIT_CORRECTION}),
    AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE: frozenset(
        {AnamnesisUpdateReason.EXPLICIT_CORRECTION}
    ),
}

#: Un update nunca puede proponer un estado de laguna: eso no representa
#: información nueva (RFC técnico de 6.5, §6 del encargo de 6.5.1).
_GAP_STATUSES = frozenset({AnamnesisFieldStatus.NO_PREGUNTADO, AnamnesisFieldStatus.NO_DETERMINADO})


class InvalidAnamnesisUpdateError(Exception):
    """Una propuesta de actualización de anamnesis viola las reglas de
    transición, contiene un campo desconocido/duplicado, o el documento
    materializado no cumple el esquema cerrado — ver §5/§9/§10/§11 del
    encargo de 6.5.1. `errors` son mensajes ya seguros (nombres de campo,
    nunca contenido clínico), mismo criterio que `SchemaValidationResult`.
    Excepción de dominio pequeña y local — nunca HTTP aquí, nunca una
    jerarquía nueva (6.5.1 es dominio puro)."""

    def __init__(self, message: str, *, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


def validate_update_batch(updates: Sequence[AnamnesisFieldUpdate]) -> None:
    """Valida la lista completa de cambios propuestos. NO interpreta
    lenguaje natural — recibe cambios ya propuestos por un generador
    (6.5.2+) y solo comprueba que sean coherentes: campo reconocido, sin
    duplicados, `reason` compatible con `previous_status`,
    `proposed_status` nunca una laguna, cambio no-op rechazado.

    Lanza `InvalidAnamnesisUpdateError` con TODOS los errores encontrados
    (nunca solo el primero) si algo falla. Una lista vacía es válida:
    "sin cambios propuestos" es un resultado legítimo (RFC técnico de
    6.5, §7 del encargo), no un error."""
    errors: list[str] = []
    seen_fields: set[str] = set()
    for update in updates:
        errors.extend(_validate_single_update(update, seen_fields))
        seen_fields.add(update.field_name)

    if errors:
        raise InvalidAnamnesisUpdateError(
            "La propuesta de actualización de anamnesis contiene cambios inválidos.",
            errors=errors,
        )


def _validate_single_update(update: AnamnesisFieldUpdate, seen_fields: set[str]) -> list[str]:
    path = f"content.{update.field_name}"

    if update.field_name not in ANAMNESIS_FIELDS:
        return [f"{path} no es un campo de anamnesis reconocido."]

    if update.field_name in seen_fields:
        return [f"{path} aparece más de una vez en la misma propuesta."]

    if update.proposed_status in _GAP_STATUSES:
        return [
            f"{path}.proposed_status='{update.proposed_status.value}' no representa "
            "información nueva; un update nunca puede proponer un estado de laguna."
        ]

    if not update.source_excerpt or not update.source_excerpt.strip():
        return [f"{path}.source_excerpt es obligatorio y no puede estar vacío."]

    allowed_reasons = _ALLOWED_REASONS_BY_PREVIOUS_STATUS.get(update.previous_status, frozenset())
    if update.reason not in allowed_reasons:
        return [
            f"{path}: reason='{update.reason.value}' no es válido para "
            f"previous_status='{update.previous_status.value}'."
        ]

    if (
        update.previous_status == update.proposed_status
        and update.previous_value == update.proposed_value
    ):
        return [f"{path} no representa ningún cambio (no-op)."]

    return []


@dataclass(slots=True, frozen=True)
class AnamnesisUpdateGroundingResult:
    ok: bool
    #: `None` si `ok` es `False`, o si `ok` es `True` pero la lista de
    #: updates estaba vacía (nada que agregar) — mismo criterio que
    #: `_build_source_map` (`(source_map or None)`).
    source_map: dict[str, Any] | None
    failure_reason: AIGenerationFailureReason | None
    ungrounded_fields: tuple[str, ...] = ()


def verify_update_grounding(
    updates: Sequence[AnamnesisFieldUpdate], current_transcript: str
) -> AnamnesisUpdateGroundingResult:
    """Grounding ACOTADO: verifica `source_excerpt` únicamente de los
    campos efectivamente propuestos en `updates`, contra el transcript de
    la sesión ACTUAL. Reutiliza `verify_excerpt()` campo a campo — nunca
    recibe la anamnesis previa como `current_transcript` (eso violaría
    RFC §5.3: "no se acepta un fragmento del contexto longitudinal como
    grounding actual"); ese control es responsabilidad del llamador
    (6.5.2+), este primitivo simplemente nunca ve ese texto.

    No modifica `GroundingValidator`/`validate_generated_content()`: no
    los invoca, no cambia su comportamiento para ningún otro
    `artifact_type`."""
    ungrounded: list[str] = []
    source_map: dict[str, Any] = {}

    for update in updates:
        result = verify_excerpt(update.source_excerpt, current_transcript)
        if not result.grounded:
            ungrounded.append(update.field_name)
            continue

        entry: dict[str, Any] = {"field": update.field_name, "excerpt": update.source_excerpt}
        if result.original_start is not None:
            entry["original_start"] = result.original_start
            entry["original_end"] = result.original_end
        source_map[update.field_name] = entry

    if ungrounded:
        return AnamnesisUpdateGroundingResult(
            ok=False,
            source_map=None,
            failure_reason=AIGenerationFailureReason.GROUNDING_FAILED,
            ungrounded_fields=tuple(ungrounded),
        )
    return AnamnesisUpdateGroundingResult(
        ok=True, source_map=(source_map or None), failure_reason=None
    )


def materialize_anamnesis(
    baseline_content: dict[str, Any], updates: Sequence[AnamnesisFieldUpdate]
) -> dict[str, Any]:
    """baseline completo + lista YA VALIDADA de `AnamnesisFieldUpdate` ->
    `content` final de ANAMNESIS. Pura: nunca muta `baseline_content`
    (copia profunda antes de aplicar cualquier cambio). Debe llamarse
    siempre después de `validate_update_batch()` — no repite esas reglas.

    Comprobación adicional, no pedida literalmente pero necesaria para
    la garantía de seguridad clínica del propio hito ("no sobrescribe
    hechos previos sin corrección explícita"): si `update.previous_value`/
    `previous_status` no coinciden con el valor REAL de ese campo en
    `baseline_content`, la propuesta se basa en una lectura del baseline
    que ya no es cierta (p. ej. un generador que declarase
    `previous_status=no_preguntado` para un campo que en realidad ya es
    `informado`, colándose por la regla de `fills_gap`) — se rechaza
    explícitamente en vez de aplicar un cambio sobre una premisa falsa."""
    materialized = copy.deepcopy(baseline_content)

    consistency_errors: list[str] = []
    for update in updates:
        baseline_field = materialized.get(update.field_name)
        if not isinstance(baseline_field, dict):
            consistency_errors.append(
                f"content.{update.field_name} no existe en el baseline recibido."
            )
            continue
        if (
            baseline_field.get("value") != update.previous_value
            or baseline_field.get("status") != update.previous_status.value
        ):
            consistency_errors.append(
                f"content.{update.field_name}: previous_value/previous_status declarados "
                "no coinciden con el estado real del baseline."
            )
    if consistency_errors:
        raise InvalidAnamnesisUpdateError(
            "La propuesta de actualización no es consistente con el baseline recibido.",
            errors=consistency_errors,
        )

    for update in updates:
        materialized[update.field_name] = {
            "value": update.proposed_value,
            "status": update.proposed_status.value,
            "source_excerpt": update.source_excerpt,
        }

    schema_result = validate_content_schema(AIArtifactType.ANAMNESIS, materialized)
    if not schema_result.valid:
        raise InvalidAnamnesisUpdateError(
            "El documento ANAMNESIS materializado no cumple el esquema cerrado.",
            errors=list(schema_result.errors),
        )
    return materialized


def changed_field_names(
    baseline_content: dict[str, Any], materialized_content: dict[str, Any]
) -> list[str]:
    """Diferencia estructural entre un baseline y un documento ANAMNESIS
    materializado (Hito 6.5.3) — usada por el servicio para construir la
    respuesta de la API y la metadata de auditoría sin necesitar acceso a
    la lista original de `AnamnesisFieldUpdate` (que `PipelineStepOutcome`
    no transporta). Comparación por igualdad estructural completa de cada
    campo (`value`/`status`/`source_excerpt`), no solo por nombre —
    reutilizable independientemente de qué produjo `materialized_content`."""
    return [
        name
        for name in ANAMNESIS_FIELDS
        if materialized_content.get(name) != baseline_content.get(name)
    ]


def reason_for_previous_status(previous_status: AnamnesisFieldStatus) -> AnamnesisUpdateReason:
    """Reconstruye el `reason` de un campo cambiado a partir de su
    `previous_status` real en el baseline — única fuente de verdad
    (`_ALLOWED_REASONS_BY_PREVIOUS_STATUS`), determinista porque cada
    `previous_status` admite exactamente un `reason` (§5 del encargo de
    6.5.1). Usada por el servicio para la metadata de auditoría (§10 del
    encargo de 6.5.3) sin duplicar esta regla."""
    return next(iter(_ALLOWED_REASONS_BY_PREVIOUS_STATUS[previous_status]))
