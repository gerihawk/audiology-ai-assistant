"""Validación estructural de `content` por `AIArtifactType` — fuente de
verdad única de la forma cerrada de cada artefacto (ver docs/fase-6-rfc.md
§4 y el encargo de la Fase 6.1, punto 4).

Cubre únicamente los tipos ya implementados y con estructura cerrada hoy:
`TRANSCRIPT`, `SUMMARY`, `CLINICAL_FLAGS`, `MISSING_INFORMATION`,
`ANAMNESIS`. `PATIENT_SUMMARY`/`SESSION_NOTES` no existen todavía en
`AIArtifactType` (hito 6.4) — no se les inventa un esquema aquí.

`ANAMNESIS` valida la estructura cerrada de HOY: 20 campos de
`ANAMNESIS_FIELDS`, cada uno `{"value": str, "status": <enum>}`. El
`source_excerpt` obligatorio para `informado`/`negado_explicitamente`
(RFC §4.6) llega cuando `AnamnesisGenerator` lo produzca de verdad — hito
6.4 ("ANAMNESIS con grounding real"), no antes: `GroundingValidator` no
puede exigir un campo que la propia estructura cerrada de este hito no
declara.

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

_ANAMNESIS_STATUSES = frozenset(status.value for status in AnamnesisFieldStatus)


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
        errors += _check_object(
            field_value, f"content.{field_name}", required={"value": str, "status": str}
        )
        status = field_value.get("status") if isinstance(field_value, dict) else None
        if isinstance(status, str) and status not in _ANAMNESIS_STATUSES:
            errors.append(f"content.{field_name}.status no es un estado de anamnesis válido.")

    return _fail(errors) if errors else _ok()


_VALIDATORS: dict[AIArtifactType, Callable[[Any], SchemaValidationResult]] = {
    AIArtifactType.TRANSCRIPT: _validate_transcript,
    AIArtifactType.SUMMARY: _validate_summary,
    AIArtifactType.CLINICAL_FLAGS: _validate_clinical_flags,
    AIArtifactType.MISSING_INFORMATION: _validate_missing_information,
    AIArtifactType.ANAMNESIS: _validate_anamnesis,
}


def validate_content_schema(artifact_type: AIArtifactType, content: Any) -> SchemaValidationResult:
    validator = _VALIDATORS.get(artifact_type)
    if validator is None:
        raise UnsupportedArtifactTypeError(artifact_type)
    return validator(content)
