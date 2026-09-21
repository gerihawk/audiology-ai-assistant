"""Métricas deterministas de generación — encargo de la Fase 6.2 §5.

Reutiliza directamente lo que ya existe en vez de duplicarlo:

- **Schema validity / grounding / safety**: `validate_generated_content`
  (`app.ai_pipeline.domain.validation_pipeline`) — invocado por
  `runner.py`, nunca reimplementado aquí.
- **Terminología / negaciones / lateralidad**: los mismos evaluadores
  deterministas del benchmark de transcripción
  (`benchmark.metrics.terminology`/`negation`/`laterality`), reutilizados
  tal cual sobre el texto aplanado del contenido generado — mismo motor,
  cero reimplementación.

Lo único nuevo aquí es lo que no existía: preservación de hechos
obligatorios, alucinación de hechos prohibidos, exactitud numérica (mismo
principio de patrones explícitos que negación/lateralidad, nunca NLP) y
completitud de `missing_information`. Sin heurísticas de comprensión
semántica en ningún caso — solo lo declarado explícitamente en
`metadata.json` (encargo §5, "no intentes resolver hallucination
semántica general con heurísticas frágiles")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.ai_pipeline.domain.content_walk import iter_dict_nodes, iter_string_leaves
from app.ai_pipeline.domain.entities import AIArtifactType
from app.core.text_normalize import normalize_text
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS
from benchmark.generation.case_metadata import FactCase, NumericCase


def flatten_content_text(content: Any) -> str:
    """Concatena todos los strings hoja de `content` — misma primitiva
    genérica que ya usan `SafetyValidator`/`detect_evasive_response`
    (`content_walk.iter_string_leaves`), nunca un recorrido nuevo."""
    return " ".join(text for _, text in iter_string_leaves(content))


def flatten_missing_information_topics(content: Any) -> str:
    """Concatena únicamente `items[].topic` de un `content` de
    `MISSING_INFORMATION` — nunca `suggested_question`.

    `topic` es lo único que declara explícitamente qué gap afirma el
    modelo; `suggested_question` es redacción auxiliar que puede
    mencionar legítimamente conceptos ya cubiertos al formular una
    pregunta de seguimiento más concreta (encargo Fase 6.2, diagnóstico
    post-mortem 2026-08-12: los falsos positivos de `forbidden_facts`
    venían de comprobar todo el output aplanado, incluida la pregunta).
    Uso exclusivo de `evaluate_forbidden_facts` en `runner.py` para este
    artifact_type — `evaluate_missing_information_completeness` sigue
    usando `topic + suggested_question` deliberadamente (pregunta
    distinta: si el modelo identificó el gap, no cómo tituló el topic).

    Mismo manejo defensivo de estructuras inválidas que
    `evaluate_missing_information_completeness` — nunca lanza, nunca
    asume forma."""
    items = content.get("items") if isinstance(content, dict) else None
    topics = (item.get("topic") for item in (items or []) if isinstance(item, dict))
    return " ".join(topic for topic in topics if isinstance(topic, str))


def _matches_any(haystack_padded: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized and f" {normalized} " in haystack_padded:
            return pattern
    return None


def _padded(text: str) -> str:
    return f" {normalize_text(text)} "


# --- Fact preservation / hallucination -----------------------------------


@dataclass(slots=True, frozen=True)
class FactCheckDetail:
    description: str
    matched: bool
    matched_pattern: str | None


@dataclass(slots=True, frozen=True)
class FactPreservationReport:
    present: int
    missing: int
    details: list[FactCheckDetail]


@dataclass(slots=True, frozen=True)
class HallucinationReport:
    forbidden_found: int
    details: list[FactCheckDetail]


def evaluate_required_facts(generated_text: str, cases: list[FactCase]) -> FactPreservationReport:
    haystack = _padded(generated_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in cases
    ]
    present = sum(1 for d in details if d.matched)
    return FactPreservationReport(present=present, missing=len(details) - present, details=details)


def evaluate_forbidden_facts(generated_text: str, cases: list[FactCase]) -> HallucinationReport:
    haystack = _padded(generated_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in cases
    ]
    forbidden_found = sum(1 for d in details if d.matched)
    return HallucinationReport(forbidden_found=forbidden_found, details=details)


# --- Numeric accuracy ------------------------------------------------------

NumericResultValue = Literal["pass", "fail", "not_detected"]


@dataclass(slots=True, frozen=True)
class NumericCaseResult:
    concept: str
    result: NumericResultValue
    matched_pattern: str | None


@dataclass(slots=True, frozen=True)
class NumericReport:
    passed: int
    failed: int
    details: list[NumericCaseResult]


def evaluate_numeric(generated_text: str, cases: list[NumericCase]) -> NumericReport:
    haystack = _padded(generated_text)
    details: list[NumericCaseResult] = []
    for case in cases:
        matched_expected = _matches_any(haystack, case.expected_patterns)
        if matched_expected:
            details.append(
                NumericCaseResult(
                    concept=case.concept, result="pass", matched_pattern=matched_expected
                )
            )
            continue
        matched_incorrect = _matches_any(haystack, case.incorrect_patterns)
        if matched_incorrect:
            details.append(
                NumericCaseResult(
                    concept=case.concept, result="fail", matched_pattern=matched_incorrect
                )
            )
            continue
        details.append(
            NumericCaseResult(concept=case.concept, result="not_detected", matched_pattern=None)
        )

    passed = sum(1 for d in details if d.result == "pass")
    failed = sum(1 for d in details if d.result == "fail")
    return NumericReport(passed=passed, failed=failed, details=details)


# --- Missing information completeness --------------------------------------


@dataclass(slots=True, frozen=True)
class MissingInformationCompletenessReport:
    expected_present: int
    expected_missing: int
    details: list[FactCheckDetail]


def evaluate_missing_information_completeness(
    content: dict[str, Any], expected_topics: list[FactCase]
) -> MissingInformationCompletenessReport:
    items = content.get("items") if isinstance(content, dict) else None
    items_text = " ".join(
        f"{item.get('topic', '')} {item.get('suggested_question', '')}"
        for item in (items or [])
        if isinstance(item, dict)
    )
    haystack = _padded(items_text)
    details = [
        FactCheckDetail(
            description=case.description,
            matched=(match := _matches_any(haystack, case.patterns)) is not None,
            matched_pattern=match,
        )
        for case in expected_topics
    ]
    present = sum(1 for d in details if d.matched)
    return MissingInformationCompletenessReport(
        expected_present=present, expected_missing=len(details) - present, details=details
    )


# --- Required evidence coverage --------------------------------------------


@dataclass(slots=True, frozen=True)
class EvidenceCoverageReport:
    fields_declaring_evidence: int
    fields_with_valid_evidence: int

    @property
    def coverage(self) -> float:
        return self.fields_with_valid_evidence / self.fields_declaring_evidence


def evaluate_evidence_coverage(
    content: Any, source_map: dict[str, Any] | None
) -> EvidenceCoverageReport | None:
    """`None` si el contenido no declara ningún `source_excerpt` — hoy es
    siempre el caso para `SUMMARY`/`MISSING_INFORMATION`/`PATIENT_SUMMARY`
    (ninguno de los tres tiene ese campo en su schema cerrado, ver
    `app/ai_pipeline/domain/schemas.py`), así que este metric queda
    deliberadamente `null` en el alcance del hito 6.2 — se activará solo
    cuando un `artifact_type` con `source_excerpt` real entre en el
    benchmark (p. ej. `SESSION_NOTES`, hito 6.4)."""
    declared = sum(
        1 for _, node in iter_dict_nodes(content) if node.get("source_excerpt") is not None
    )
    if declared == 0:
        return None
    valid = len(source_map or {})
    return EvidenceCoverageReport(
        fields_declaring_evidence=declared, fields_with_valid_evidence=valid
    )


# --- Coincidencia de status por campo (ANAMNESIS/SESSION_NOTES) ------------
#
# hito 6.4.4 (docs/fase-6-4-4-anamnesis-benchmark-rfc.md §2): el grounding
# estructural (`_build_source_map`) y la consistencia evidencia/estado
# (`schemas.py::_check_*_evidence_consistency`) ya bloquean que un modelo
# invente una cita para un campo — lo que NO detectan es que la cita sea
# real pero irrelevante para ese campo concreto (`status_escalation`, el
# modelo "se inventa" haber recibido información) o que el modelo omita
# información que la referencia dice que sí se aportó (`status_downgrade`).
# Comparación exacta de un enum cerrado — nunca heurística de texto libre.

FieldStatusOutcome = Literal["match", "status_escalation", "status_downgrade", "status_mismatch"]

#: SESSION_NOTES no tiene un enum de `status` explícito (ver
#: `SessionNotesBlock`) — `reported`/`not_reported` es un status derivado
#: de `text` vacío o no, pero cae en la misma partición evidencia/sin-
#: evidencia que los 4 estados de ANAMNESIS.
_EVIDENCE_STATUSES = frozenset({"informado", "negado_explicitamente", "reported"})
_NO_EVIDENCE_STATUSES = frozenset({"no_preguntado", "no_determinado", "not_reported"})


@dataclass(slots=True, frozen=True)
class FieldStatusDetail:
    field: str
    critical: bool
    reference_status: str
    generated_status: str
    outcome: FieldStatusOutcome


@dataclass(slots=True, frozen=True)
class FieldMatchReport:
    details: list[FieldStatusDetail]

    @property
    def critical_escalations(self) -> int:
        return sum(1 for d in self.details if d.critical and d.outcome == "status_escalation")

    @property
    def critical_downgrades(self) -> int:
        return sum(1 for d in self.details if d.critical and d.outcome == "status_downgrade")

    @property
    def noncritical_escalations(self) -> int:
        return sum(1 for d in self.details if not d.critical and d.outcome == "status_escalation")

    @property
    def noncritical_downgrades(self) -> int:
        return sum(1 for d in self.details if not d.critical and d.outcome == "status_downgrade")

    @property
    def mismatches(self) -> int:
        return sum(1 for d in self.details if d.outcome == "status_mismatch")


def _status_group(status: str) -> Literal["evidence", "no_evidence"]:
    return "evidence" if status in _EVIDENCE_STATUSES else "no_evidence"


def _classify_status_pair(reference_status: str, generated_status: str) -> FieldStatusOutcome:
    if reference_status == generated_status:
        return "match"
    reference_group = _status_group(reference_status)
    generated_group = _status_group(generated_status)
    if reference_group == generated_group:
        # Mismo grupo, valor distinto (p. ej. informado <-> negado_explicitamente,
        # o no_preguntado <-> no_determinado): ni fabrica ni omite desde cero,
        # invierte el sentido dentro del mismo nivel de evidencia.
        return "status_mismatch"
    if reference_group == "no_evidence" and generated_group == "evidence":
        return "status_escalation"
    return "status_downgrade"


def _anamnesis_field_statuses(content: Any) -> dict[str, str]:
    if not isinstance(content, dict):
        return {}
    statuses: dict[str, str] = {}
    for field_name in ANAMNESIS_FIELDS:
        field_value = content.get(field_name)
        status = field_value.get("status") if isinstance(field_value, dict) else None
        if isinstance(status, str):
            statuses[field_name] = status
    return statuses


def _session_notes_block_statuses(content: Any) -> dict[str, str]:
    if not isinstance(content, dict):
        return {}
    statuses: dict[str, str] = {}
    for block_name in SESSION_NOTES_BLOCKS:
        block = content.get(block_name)
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        statuses[block_name] = (
            "reported" if isinstance(text, str) and text.strip() else "not_reported"
        )
    return statuses


def evaluate_field_status_match(
    *,
    artifact_type: AIArtifactType,
    generated_content: Any,
    reference_content: Any,
    critical_fields: frozenset[str],
) -> FieldMatchReport | None:
    """`None` para cualquier `artifact_type` distinto de ANAMNESIS/
    SESSION_NOTES (hito 6.4.4, exclusivo de estos dos — ver
    docs/fase-6-4-4-anamnesis-benchmark-rfc.md §2). Solo compara campos
    presentes en AMBOS contenidos: un campo ausente por fallo estructural ya
    lo captura `schema_gate`, nunca este metric."""
    if artifact_type is AIArtifactType.ANAMNESIS:
        reference_statuses = _anamnesis_field_statuses(reference_content)
        generated_statuses = _anamnesis_field_statuses(generated_content)
    elif artifact_type is AIArtifactType.SESSION_NOTES:
        reference_statuses = _session_notes_block_statuses(reference_content)
        generated_statuses = _session_notes_block_statuses(generated_content)
    else:
        return None

    details = [
        FieldStatusDetail(
            field=field_name,
            critical=field_name in critical_fields,
            reference_status=reference_statuses[field_name],
            generated_status=generated_statuses[field_name],
            outcome=_classify_status_pair(
                reference_statuses[field_name], generated_statuses[field_name]
            ),
        )
        for field_name in sorted(set(reference_statuses) & set(generated_statuses))
    ]
    return FieldMatchReport(details=details)
