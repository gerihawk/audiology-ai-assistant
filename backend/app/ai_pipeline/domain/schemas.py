"""Validación estructural de `content` por `AIArtifactType` — fuente de
verdad única de la forma cerrada de cada artefacto (ver docs/fase-6-rfc.md
§4 y el encargo de la Fase 6.1, punto 4).

Cubre únicamente los tipos ya implementados y con estructura cerrada hoy:
`TRANSCRIPT`, `SUMMARY`, `CLINICAL_FLAGS`, `MISSING_INFORMATION`,
`ANAMNESIS`, `PATIENT_SUMMARY`, `SESSION_NOTES`.

`PATIENT_SUMMARY` (contrato cerrado por docs/fase-6-rfc.md §4.3, hito 6.2
— precondición de arquitectura): `{"text": str}`, misma forma que
`SUMMARY` porque la RFC declara la misma salida ("lenguaje llano") sin
más estructura. No implica que el artefacto se genere ya en producción —
sigue sin `PipelineStep` ni entrada en `PIPELINE_STEP_ORDER` (hito 6.3).

`ANAMNESIS` valida la estructura cerrada de HOY (Fase 6.4.2): 20 campos de
`ANAMNESIS_FIELDS`, cada uno `{"value": str, "status": <enum>,
"source_excerpt": str | None}` — `source_excerpt` es una clave obligatoria
presente y nullable (mismo patrón que `clinical_flags[].source_excerpt`),
nunca opcional/ausente. Además de la validación estructural genérica
(`_check_object`), `_check_anamnesis_evidence_consistency` aplica una
segunda fase específica de ANAMNESIS (RFC técnico de 6.4, §6): `status`
en `informado`/`negado_explicitamente` exige `source_excerpt` no vacío;
`status` en `no_preguntado`/`no_determinado` exige `source_excerpt=None`
— nunca una cita inventada. Esta regla vive fuera de `_check_object` a
propósito: ese helper es y sigue siendo un validador estructural puro
(claves/tipos), sin conocer semántica de negocio de ningún artefacto.

`SESSION_NOTES` (Fase 6.4.3, RFC técnico §8): 4 bloques cerrados de
`SESSION_NOTES_BLOCKS`, cada uno `{"text": str, "source_excerpt": str |
None}` — mismo patrón de clave obligatoria-presente-nullable.
`_check_session_notes_evidence_consistency` aplica la regla cruzada
equivalente: `text` no vacío exige `source_excerpt` no vacío; `text`
vacío (`""`, el único valor que representa "bloque no explorado" — RFC
§4.7) exige `source_excerpt=None`. Sin enum de estado — a diferencia de
ANAMNESIS, `SESSION_NOTES` no lo declara.

Rechaza: campos obligatorios ausentes, tipos incorrectos, enums
inválidos, estructura anidada inválida y campos desconocidos (contrato
cerrado). Nunca incluye en los mensajes de error el valor recibido —
solo nombres de campo y tipos esperados (ver §13, nada sensible en
logs/errores)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS, AnamnesisFieldStatus
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS

_ANAMNESIS_STATUSES = frozenset(status.value for status in AnamnesisFieldStatus)

#: Estados que exigen `source_excerpt` no vacío — RFC técnico de 6.4 §6.
_STATUSES_REQUIRING_EVIDENCE = frozenset(
    {AnamnesisFieldStatus.INFORMADO.value, AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE.value}
)


class UnsupportedArtifactTypeError(Exception):
    """No existe un esquema registrado para este `artifact_type` — ver
    encargo de la Fase 6.1, punto 7 ("unsupported artifact type")."""

    def __init__(self, artifact_type: AIArtifactType) -> None:
        super().__init__(f"Sin esquema registrado para artifact_type={artifact_type}.")
        self.artifact_type = artifact_type


@dataclass(slots=True, frozen=True)
class SchemaValidationResult:
    valid: bool
    errors: tuple[str, ...]


def _ok() -> SchemaValidationResult:
    return SchemaValidationResult(valid=True, errors=())


def _fail(errors: list[str]) -> SchemaValidationResult:
    return SchemaValidationResult(valid=False, errors=tuple(errors))


def _check_object(
    value: Any,
    path: str,
    *,
    required: dict[str, type | tuple[type, ...]],
    optional: dict[str, type | tuple[type, ...]] | None = None,
) -> list[str]:
    """Valida que `value` sea un dict con exactamente las claves de
    `required`/`optional` (nunca más, nunca campos obligatorios ausentes)
    y que cada valor presente tenga el tipo declarado. `bool` se excluye
    deliberadamente de los `int` aceptados (`isinstance(True, int)` es
    `True` en Python, pero un booleano nunca es un entero clínico válido
    aquí)."""
    if not isinstance(value, dict):
        return [f"{path} debe ser un objeto."]

    optional = optional or {}
    allowed = set(required) | set(optional)
    errors: list[str] = [
        f"{path}.{key} es un campo desconocido." for key in value if key not in allowed
    ]

    for key, expected_type in required.items():
        if key not in value:
            errors.append(f"Falta el campo obligatorio {path}.{key}.")
        elif not _is_type(value[key], expected_type):
            errors.append(f"{path}.{key} tiene un tipo inválido.")
    for key, expected_type in optional.items():
        if key in value and value[key] is not None and not _is_type(value[key], expected_type):
            errors.append(f"{path}.{key} tiene un tipo inválido.")
    return errors


def _is_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if isinstance(value, bool) and expected in (int, (int,)):
        return False
    return isinstance(value, expected)


def _validate_transcript(content: Any) -> SchemaValidationResult:
    errors = _check_object(
        content,
        "content",
        required={"text": str, "language": str},
        optional={"duration_ms": int, "segments": list},
    )
    if isinstance(content, dict) and isinstance(content.get("segments"), list):
        for index, segment in enumerate(content["segments"]):
            errors += _check_object(
                segment,
                f"content.segments[{index}]",
                required={
                    "speaker": (str, type(None)),
                    "start_ms": int,
                    "end_ms": int,
                    "text": str,
                },
            )
    return _fail(errors) if errors else _ok()


def _validate_summary(content: Any) -> SchemaValidationResult:
    errors = _check_object(content, "content", required={"text": str})
    return _fail(errors) if errors else _ok()


def _validate_clinical_flags(content: Any) -> SchemaValidationResult:
    errors = _check_object(content, "content", required={"flags": list})
    if isinstance(content, dict) and isinstance(content.get("flags"), list):
        for index, flag in enumerate(content["flags"]):
            errors += _check_object(
                flag,
                f"content.flags[{index}]",
                required={
                    "category": str,
                    "description": str,
                    "source_excerpt": (str, type(None)),
                    "ruleset_name": str,
                },
            )
    return _fail(errors) if errors else _ok()


def _validate_patient_summary(content: Any) -> SchemaValidationResult:
    errors = _check_object(content, "content", required={"text": str})
    return _fail(errors) if errors else _ok()


def _validate_missing_information(content: Any) -> SchemaValidationResult:
    errors = _check_object(content, "content", required={"items": list})
    if isinstance(content, dict) and isinstance(content.get("items"), list):
        for index, item in enumerate(content["items"]):
            errors += _check_object(
                item,
                f"content.items[{index}]",
                required={"topic": str, "suggested_question": str},
            )
    return _fail(errors) if errors else _ok()


def _validate_anamnesis(content: Any) -> SchemaValidationResult:
    if not isinstance(content, dict):
        return _fail(["content debe ser un objeto."])

    errors: list[str] = []
    expected_fields = set(ANAMNESIS_FIELDS)
    for unknown in set(content) - expected_fields:
        errors.append(f"content.{unknown} no es un campo de anamnesis reconocido.")
    for missing in expected_fields - set(content):
        errors.append(f"Falta el campo obligatorio de anamnesis content.{missing}.")

    for field_name in expected_fields & set(content):
        field_value = content[field_name]
        # Fase 1 — estructural pura, vía el helper genérico compartido.
        errors += _check_object(
            field_value,
            f"content.{field_name}",
            required={"value": str, "status": str, "source_excerpt": (str, type(None))},
        )
        status = field_value.get("status") if isinstance(field_value, dict) else None
        if isinstance(status, str) and status not in _ANAMNESIS_STATUSES:
            errors.append(f"content.{field_name}.status no es un estado de anamnesis válido.")
        elif isinstance(status, str) and isinstance(field_value, dict):
            # Fase 2 — cruzada status/source_excerpt, exclusiva de ANAMNESIS,
            # solo si la fase 1 ya dejó `status` en un valor reconocido.
            errors += _check_anamnesis_evidence_consistency(
                f"content.{field_name}", field_value, status
            )

    return _fail(errors) if errors else _ok()


def _check_anamnesis_evidence_consistency(
    path: str, field_value: dict[str, Any], status: str
) -> list[str]:
    """Segunda fase de validación, específica de ANAMNESIS (RFC técnico de
    6.4, §6) — nunca toca `_check_object`, que sigue siendo un validador
    estructural puro sin conocer esta regla de negocio.

    `informado`/`negado_explicitamente` exigen `source_excerpt` no vacío;
    `no_preguntado`/`no_determinado` exigen `source_excerpt=None` — nunca
    una cita inventada para un campo sin evidencia."""
    excerpt = field_value.get("source_excerpt")
    if status in _STATUSES_REQUIRING_EVIDENCE:
        if not isinstance(excerpt, str) or not excerpt.strip():
            return [
                f"{path}.source_excerpt es obligatorio y no puede estar vacío "
                f"cuando status='{status}'."
            ]
        return []
    if excerpt is not None:
        return [f"{path}.source_excerpt debe ser null cuando status='{status}'."]
    return []


def _validate_session_notes(content: Any) -> SchemaValidationResult:
    if not isinstance(content, dict):
        return _fail(["content debe ser un objeto."])

    errors: list[str] = []
    expected_blocks = set(SESSION_NOTES_BLOCKS)
    for unknown in set(content) - expected_blocks:
        errors.append(f"content.{unknown} no es un bloque de session_notes reconocido.")
    for missing in expected_blocks - set(content):
        errors.append(f"Falta el bloque obligatorio de session_notes content.{missing}.")

    for block_name in expected_blocks & set(content):
        block = content[block_name]
        # Fase 1 — estructural pura, vía el helper genérico compartido.
        errors += _check_object(
            block,
            f"content.{block_name}",
            required={"text": str, "source_excerpt": (str, type(None))},
        )
        if isinstance(block, dict):
            # Fase 2 — cruzada text/source_excerpt, exclusiva de
            # SESSION_NOTES, solo si la fase 1 ya confirmó que es un dict.
            errors += _check_session_notes_evidence_consistency(f"content.{block_name}", block)

    return _fail(errors) if errors else _ok()


def _check_session_notes_evidence_consistency(path: str, block: dict[str, Any]) -> list[str]:
    """Segunda fase de validación, específica de SESSION_NOTES (RFC
    técnico de 6.4, §8) — nunca toca `_check_object`. `text` no vacío
    exige `source_excerpt` no vacío; `text` vacío (`""`, la única
    representación de "bloque no explorado") exige `source_excerpt=None`
    — nunca una cita inventada para un bloque sin contenido."""
    text = block.get("text")
    excerpt = block.get("source_excerpt")
    text_is_present = isinstance(text, str) and text.strip() != ""

    if text_is_present:
        if not isinstance(excerpt, str) or not excerpt.strip():
            return [
                f"{path}.source_excerpt es obligatorio y no puede estar vacío "
                f"cuando {path}.text no está vacío."
            ]
        return []
    if excerpt is not None:
        return [f"{path}.source_excerpt debe ser null cuando {path}.text está vacío."]
    return []


_VALIDATORS: dict[AIArtifactType, Callable[[Any], SchemaValidationResult]] = {
    AIArtifactType.TRANSCRIPT: _validate_transcript,
    AIArtifactType.SUMMARY: _validate_summary,
    AIArtifactType.CLINICAL_FLAGS: _validate_clinical_flags,
    AIArtifactType.MISSING_INFORMATION: _validate_missing_information,
    AIArtifactType.ANAMNESIS: _validate_anamnesis,
    AIArtifactType.PATIENT_SUMMARY: _validate_patient_summary,
    AIArtifactType.SESSION_NOTES: _validate_session_notes,
}


def validate_content_schema(artifact_type: AIArtifactType, content: Any) -> SchemaValidationResult:
    validator = _VALIDATORS.get(artifact_type)
    if validator is None:
        raise UnsupportedArtifactTypeError(artifact_type)
    return validator(content)
