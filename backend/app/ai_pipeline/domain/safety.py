"""Constante compartida de lenguaje clínico prohibido y `SafetyValidator`.

Fuente normativa única: docs/clinical-safety.md §3. Producción y tests
importan esta misma constante — ver docs/fase-6-rfc.md §5.2 y §9.1
(prerrequisito 3). Prohibida la duplicación inline en otro punto del
backend o de los tests.

`SafetyValidator` (hito 6.1) recorre TODOS los valores string de hoja de
un `content` de `AIArtifactVersion` — no solo `source_excerpt` — porque
lenguaje prohibido puede colarse en cualquier campo de texto generado
(`summary.text`, `anamnesis.*.value`, `clinical_flags[].description`...).
Es determinista, no usa ningún LLM, y se invoca desde el wrapper común de
`steps/base.py` (ver §5.2) para que ningún step pueda omitirlo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai_pipeline.domain.content_walk import iter_string_leaves
from app.core.text_normalize import normalize_text

FORBIDDEN_CLINICAL_LANGUAGE: tuple[str, ...] = (
    "el paciente tiene",
    "diagnóstico confirmado",
    "tratamiento recomendado automáticamente",
)


@dataclass(slots=True, frozen=True)
class SafetyViolation:
    #: La propia expresión prohibida de `FORBIDDEN_CLINICAL_LANGUAGE` —
    #: identificador de regla estable y ya único (constante cerrada), sin
    #: necesidad de una tabla de ids adicional.
    rule: str
    #: Ruta del campo dentro de `content` (ver `content_walk.py`) — nunca
    #: se incluye el texto completo del campo, solo dónde apareció.
    field: str
    reason: str = "Lenguaje clínico prohibido — ver docs/clinical-safety.md §3."


@dataclass(slots=True, frozen=True)
class SafetyValidationResult:
    valid: bool
    violations: tuple[SafetyViolation, ...]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(violation.rule for violation in self.violations)


def validate_safety(content: object) -> SafetyValidationResult:
    """Determinista, sin LLM. Comparación insensible a mayúsculas/tildes/
    puntuación (misma normalización que `GroundingValidator`) para que
    "Diagnóstico   Confirmado" o "DIAGNÓSTICO CONFIRMADO" no la esquiven."""
    violations: list[SafetyViolation] = []
    for field_path, text in iter_string_leaves(content):
        normalized_text = normalize_text(text)
        for phrase in FORBIDDEN_CLINICAL_LANGUAGE:
            if normalize_text(phrase) in normalized_text:
                violations.append(SafetyViolation(rule=phrase, field=field_path))
    return SafetyValidationResult(valid=not violations, violations=tuple(violations))
