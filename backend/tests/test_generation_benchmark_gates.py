"""Tests de los gates clínicos jerárquicos y la clasificación de errores
— Fase 6.2 (encargo §21-22)."""

from __future__ import annotations

from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.validation_pipeline import ValidationOutcome
from benchmark.generation.case_metadata import FactCase
from benchmark.generation.gates import classify_findings, evaluate_gates
from benchmark.generation.metrics import (
    evaluate_forbidden_facts,
    evaluate_required_facts,
)
from benchmark.metrics.laterality import LateralityCaseResult, LateralityReport
from benchmark.metrics.negation import NegationCaseResult, NegationReport

_OK_VALIDATION = ValidationOutcome(
    ok=True, content={"text": "ok"}, source_map=None, failure_reason=None
)


def _schema_failed() -> ValidationOutcome:
    return ValidationOutcome(
        ok=False,
        content=None,
        source_map=None,
        failure_reason=AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED,
    )


def _safety_failed(rule_ids=("forbidden_diagnostic_language",)) -> ValidationOutcome:
    return ValidationOutcome(
        ok=False,
        content=None,
        source_map=None,
        failure_reason=AIGenerationFailureReason.SAFETY_POLICY_FAILED,
        violated_rule_ids=rule_ids,
    )


class TestEvaluateGates:
    def test_todo_pasa(self):
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=None, negations=None, laterality=None
        )
        assert result.passed_all is True
        assert result.blocking_gate is None

    def test_safety_bloquea_primero(self):
        result = evaluate_gates(
            validation=_safety_failed(), hallucination=None, negations=None, laterality=None
        )
        assert result.passed_all is False
        assert result.blocking_gate == "safety"
        assert result.safety_gate is False

    def test_schema_invalido_bloquea(self):
        result = evaluate_gates(
            validation=_schema_failed(), hallucination=None, negations=None, laterality=None
        )
        assert result.passed_all is False
        assert result.blocking_gate == "schema"

    def test_alucinacion_bloquea_aunque_schema_sea_valido(self):
        hallucination = evaluate_forbidden_facts(
            "El paciente refiere vértigo.", [FactCase(description="vértigo", patterns=["vértigo"])]
        )
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=hallucination, negations=None, laterality=None
        )
        assert result.passed_all is False
        assert result.blocking_gate == "hallucination"

    def test_negacion_invertida_bloquea(self):
        negations = NegationReport(
            passed=0,
            failed=1,
            details=[
                NegationCaseResult(
                    concept="vertigo",
                    expected="negated",
                    result="fail",
                    matched_pattern="tiene vértigo",
                )
            ],
        )
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=None, negations=negations, laterality=None
        )
        assert result.passed_all is False
        assert result.blocking_gate == "negation_laterality"

    def test_lateralidad_invertida_bloquea(self):
        laterality = LateralityReport(
            passed=0,
            failed=1,
            details=[
                LateralityCaseResult(
                    concept="tinnitus",
                    expected="left",
                    result="fail",
                    matched_pattern="oído derecho",
                    matched_laterality="right",
                )
            ],
        )
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=None, negations=None, laterality=laterality
        )
        assert result.passed_all is False
        assert result.blocking_gate == "negation_laterality"

    def test_sin_metadata_declarada_los_gates_opcionales_son_null(self):
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=None, negations=None, laterality=None
        )
        assert result.hallucination_gate is None
        assert result.negation_laterality_gate is None
        assert result.passed_all is True


class TestClassifyFindings:
    def test_safety_produce_critical(self):
        findings = classify_findings(
            validation=_safety_failed(("forbidden_diagnostic_language",)),
            hallucination=None,
            required_facts=None,
            negations=None,
            laterality=None,
            numeric=None,
            terminology=None,
            missing_information_completeness=None,
        )
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].category == "safety"

    def test_hecho_omitido_produce_major(self):
        required_facts = evaluate_required_facts(
            "texto sin nada relevante", [FactCase(description="acúfenos", patterns=["acúfenos"])]
        )
        findings = classify_findings(
            validation=_OK_VALIDATION,
            hallucination=None,
            required_facts=required_facts,
            negations=None,
            laterality=None,
            numeric=None,
            terminology=None,
            missing_information_completeness=None,
        )
        assert len(findings) == 1
        assert findings[0].severity == "major"
        assert findings[0].category == "omission"

    def test_sin_hallazgos_lista_vacia(self):
        findings = classify_findings(
            validation=_OK_VALIDATION,
            hallucination=None,
            required_facts=None,
            negations=None,
            laterality=None,
            numeric=None,
            terminology=None,
            missing_information_completeness=None,
        )
        assert findings == []

    def test_missing_topic_false_positive_produce_major_no_critical(self):
        # Diagnóstico post-mortem 2026-08-12: un topic de MISSING_INFORMATION
        # que coincide con un forbidden_fact es MAJOR (calidad de la
        # propuesta), nunca CRITICAL/`hallucination` — el modelo no afirma
        # ningún hecho fabricado, solo propone revisitar algo ya cubierto.
        missing_topic_false_positives = evaluate_forbidden_facts(
            "uso de protección auditiva y exposición laboral",
            [FactCase(description="exposición laboral", patterns=["exposición laboral"])],
        )
        findings = classify_findings(
            validation=_OK_VALIDATION,
            hallucination=None,
            required_facts=None,
            negations=None,
            laterality=None,
            numeric=None,
            terminology=None,
            missing_information_completeness=None,
            missing_topic_false_positives=missing_topic_false_positives,
        )
        assert len(findings) == 1
        assert findings[0].severity == "major"
        assert findings[0].category == "missing_topic_false_positive"

    def test_missing_topic_false_positive_no_afecta_hallucination_gate(self):
        # `missing_topic_false_positives` nunca se pasa a `evaluate_gates`
        # (solo `hallucination` lo hace) — confirma que el routing en
        # `runner.py` es la única pieza que decide el gate, no `gates.py`.
        missing_topic_false_positives = evaluate_forbidden_facts(
            "exposición laboral", [FactCase(description="x", patterns=["exposición laboral"])]
        )
        result = evaluate_gates(
            validation=_OK_VALIDATION, hallucination=None, negations=None, laterality=None
        )
        assert result.hallucination_gate is None
        assert result.passed_all is True
        assert missing_topic_false_positives.forbidden_found == 1  # detectado, solo no bloquea
