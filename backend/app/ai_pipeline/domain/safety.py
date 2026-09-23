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

Hallazgo bloqueante del red team (docs/security/red-team-app-2026-09-22.md
§A1, 2026-09-22): comparar solo contra las 3 frases literales de
`FORBIDDEN_CLINICAL_LANGUAGE` no basta — docs/clinical-safety.md §3 define
el lenguaje prohibido como un CONCEPTO ("cualquier formulación que
presente una inferencia de la IA como hecho clínico establecido"), no una
lista cerrada. `_FORBIDDEN_PATTERNS` amplía la detección con patrones
estructurales (sujeto+verbo diagnóstico, variantes reordenadas/con huecos
de "diagnóstico confirmado" y "tratamiento ... automático", e inglés)
manteniendo el mismo criterio determinista/sin-LLM. `FORBIDDEN_CLINICAL_LANGUAGE`
se mantiene tal cual (backward-compat: `tests/test_ai_pipeline_api.py`
sigue haciendo `phrase not in rendered.lower()` con ella directamente) y
sigue siendo el primer bloque de `_FORBIDDEN_PATTERNS`, así que el `rule`
reportado para esas 3 frases exactas no cambia.

Límite conocido, deliberado: no cubre una afirmación diagnóstica plana sin
ninguna palabra ancla ("paciente", "diagnóstico", "tratamiento", "patient",
"diagnosis") — p. ej. "Hipoacusia neurosensorial bilateral confirmada
mediante audiometría." Cerrar ese caso sin una lista abierta de términos
médicos (mantenimiento inacabable) o sin falsos positivos sobre lenguaje
legítimo ("posible hipoacusia a confirmar en consulta") requiere la capa
semántica de auditoría propuesta como Paso 2 — no se fuerza aquí un patrón
demasiado amplio para cerrarlo de forma determinista.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.ai_pipeline.domain.content_walk import iter_string_leaves
from app.core.text_normalize import normalize_text

FORBIDDEN_CLINICAL_LANGUAGE: tuple[str, ...] = (
    "el paciente tiene",
    "diagnóstico confirmado",
    "tratamiento recomendado automáticamente",
)


def _strip_accents(text: str) -> str:
    """Quita diacríticos (NFD, descarta marcas combinantes Unicode).

    Uso EXCLUSIVO de este módulo. `normalize_text` (app/core/text_normalize.py)
    deliberadamente no elimina tildes — lo comparte con el cálculo de WER de
    transcripción y con `GroundingValidator`, donde una tilde real importa.
    Aquí sí interesa ser insensible a tildes: un LLM puede omitirlas en una
    reformulación y eso no debe ser una vía de bypass de un gate de
    seguridad clínica."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _safety_normalize(text: str) -> str:
    return _strip_accents(normalize_text(text))


#: Hueco tolerado entre dos anclas de un mismo patrón (p. ej. "el paciente,
#: según el análisis del sistema, tiene" — 5 palabras insertadas). Los
#: patrones ya se comparan sobre texto sin tildes (`_safety_normalize`).
_GAP = r"(?:\s+\S+){0,6}\s+"


@dataclass(frozen=True, slots=True)
class _ForbiddenPattern:
    rule: str
    regex: re.Pattern[str]


def _literal(rule: str) -> _ForbiddenPattern:
    return _ForbiddenPattern(rule=rule, regex=re.compile(re.escape(_safety_normalize(rule))))


_PACIENTE_VERBOS = r"(?:tiene|sufre|padece|presenta)"
_DIAGNOSTICO_VARIANTE = "diagnóstico confirmado (variante/reformulación)"
_TRATAMIENTO_VARIANTE = "tratamiento recomendado automáticamente (variante/reformulación)"
_INGLES_PACIENTE = "the patient has/suffers/presents (equivalente inglés)"
_INGLES_DIAGNOSTICO = "diagnosis confirmed (equivalente inglés)"

# Orden deliberado: las 3 frases literales van primero para que, cuando el
# texto las contiene tal cual, `violation.rule` siga siendo exactamente esa
# frase (compatibilidad con tests existentes) — `validate_safety` solo
# reporta la PRIMERA regla que coincide por campo, nunca duplica.
_FORBIDDEN_PATTERNS: tuple[_ForbiddenPattern, ...] = (
    *(_literal(phrase) for phrase in FORBIDDEN_CLINICAL_LANGUAGE),
    # "el paciente [hasta 6 palabras] tiene/sufre/padece/presenta"
    _ForbiddenPattern(
        rule="el paciente + verbo diagnóstico (tiene/sufre/padece/presenta)",
        regex=re.compile(rf"\bel paciente\b{_GAP}\b{_PACIENTE_VERBOS}\b"),
    ),
    # orden invertido: "tiene/sufre/padece/presenta ... el paciente"
    _ForbiddenPattern(
        rule="el paciente + verbo diagnóstico (tiene/sufre/padece/presenta)",
        regex=re.compile(rf"\b{_PACIENTE_VERBOS}\b{_GAP}\bel paciente\b"),
    ),
    # "diagnóstico ... confirmado" y su inverso, con hueco tolerado
    _ForbiddenPattern(
        rule=_DIAGNOSTICO_VARIANTE,
        regex=re.compile(rf"\bdiagnostic\w*\b{_GAP}\bconfirmad\w*\b"),
    ),
    _ForbiddenPattern(
        rule=_DIAGNOSTICO_VARIANTE,
        regex=re.compile(rf"\bconfirm\w*\b{_GAP}\bdiagnostic\w*\b"),
    ),
    # "tratamiento ... recomendado ... automático" en cualquier orden/hueco
    _ForbiddenPattern(
        rule=_TRATAMIENTO_VARIANTE,
        regex=re.compile(rf"\btratamiento\w*\b{_GAP}\brecomendad\w*\b{_GAP}\bautomatic\w*\b"),
    ),
    _ForbiddenPattern(
        rule=_TRATAMIENTO_VARIANTE,
        regex=re.compile(rf"\brecomiend\w*\b{_GAP}\btratamiento\w*\b{_GAP}\bautomatic\w*\b"),
    ),
    # variante amplia sin exigir "recomendado": cualquier "tratamiento ...
    # automático/automáticamente" (p. ej. "el sistema asigna tratamiento
    # automáticamente"). No detecta negación ("no debe indicarse tratamiento
    # automático sin revisión") — limitación conocida de un gate por
    # proximidad de palabras, ver docstring del módulo.
    _ForbiddenPattern(
        rule=_TRATAMIENTO_VARIANTE,
        regex=re.compile(r"\btratamiento\w*\b(?:\s+\S+){0,8}\s+\bautomatic\w*\b"),
    ),
    # equivalentes en inglés
    _ForbiddenPattern(
        rule=_INGLES_PACIENTE,
        regex=re.compile(rf"\bthe patient\b{_GAP}\b(?:has|suffers|presents)\b"),
    ),
    _ForbiddenPattern(
        rule=_INGLES_DIAGNOSTICO,
        regex=re.compile(r"\bdiagnos\w*\b(?:\s+\S+){0,4}\s+\bconfirm\w*\b"),
    ),
    _ForbiddenPattern(
        rule=_INGLES_DIAGNOSTICO,
        regex=re.compile(r"\bconfirm\w*\b(?:\s+\S+){0,4}\s+\bdiagnos\w*\b"),
    ),
)


@dataclass(slots=True, frozen=True)
class SafetyViolation:
    #: Identificador de regla estable — la frase literal exacta para las 3
    #: originales de `FORBIDDEN_CLINICAL_LANGUAGE`, o una descripción del
    #: patrón estructural para el resto (ver `_FORBIDDEN_PATTERNS`).
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
    """Determinista, sin LLM. Compara cada campo de texto contra
    `_FORBIDDEN_PATTERNS` (insensible a mayúsculas/tildes/puntuación/orden
    de palabras dentro de un hueco tolerado) y reporta la PRIMERA regla que
    coincide por campo — nunca duplica violaciones para el mismo campo
    aunque varios patrones coincidan a la vez."""
    violations: list[SafetyViolation] = []
    for field_path, text in iter_string_leaves(content):
        normalized_text = _safety_normalize(text)
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.regex.search(normalized_text):
                violations.append(SafetyViolation(rule=pattern.rule, field=field_path))
                break
    return SafetyValidationResult(valid=not violations, violations=tuple(violations))
