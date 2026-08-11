"""Tests de las métricas deterministas nuevas del benchmark de generación
— Fase 6.2. Terminología/negación/lateralidad ya están cubiertas por los
tests del benchmark ASR (reutilizadas tal cual, sin duplicar aquí)."""

from __future__ import annotations

from benchmark.generation.case_metadata import FactCase, NumericCase
from benchmark.generation.metrics import (
    evaluate_evidence_coverage,
    evaluate_forbidden_facts,
    evaluate_missing_information_completeness,
    evaluate_numeric,
    evaluate_required_facts,
    flatten_content_text,
)


class TestFlattenContentText:
    def test_aplana_texto_anidado(self):
        content = {"items": [{"topic": "a", "suggested_question": "b"}]}
        assert flatten_content_text(content) == "a b"

    def test_contenido_vacio(self):
        assert flatten_content_text({}) == ""


class TestRequiredFacts:
    def test_hecho_presente(self):
        cases = [FactCase(description="pérdida en oído izquierdo", patterns=["oído izquierdo"])]
        result = evaluate_required_facts(
            "Nota pérdida en el oído izquierdo desde hace meses.", cases
        )
        assert result.present == 1
        assert result.missing == 0
        assert result.details[0].matched_pattern == "oído izquierdo"

    def test_hecho_ausente(self):
        cases = [FactCase(description="acúfenos", patterns=["acúfenos", "pitidos"])]
        result = evaluate_required_facts("Resumen sin mención de sonidos.", cases)
        assert result.present == 0
        assert result.missing == 1


class TestForbiddenFacts:
    def test_hecho_prohibido_presente_es_alucinacion(self):
        cases = [FactCase(description="vértigo", patterns=["vértigo"])]
        result = evaluate_forbidden_facts("El paciente refiere vértigo intenso.", cases)
        assert result.forbidden_found == 1
        assert result.details[0].matched is True

    def test_hecho_prohibido_ausente_es_correcto(self):
        cases = [FactCase(description="vértigo", patterns=["vértigo"])]
        result = evaluate_forbidden_facts("El paciente niega mareos.", cases)
        assert result.forbidden_found == 0


class TestNumericAccuracy:
    def test_valor_correcto(self):
        cases = [
            NumericCase(
                concept="edad",
                expected_patterns=["setenta años"],
                incorrect_patterns=["sesenta años"],
            )
        ]
        result = evaluate_numeric("El padre usa audífonos desde los setenta años.", cases)
        assert result.passed == 1
        assert result.failed == 0

    def test_valor_incorrecto(self):
        cases = [
            NumericCase(
                concept="edad",
                expected_patterns=["setenta años"],
                incorrect_patterns=["sesenta años"],
            )
        ]
        result = evaluate_numeric("El padre usa audífonos desde los sesenta años.", cases)
        assert result.passed == 0
        assert result.failed == 1

    def test_valor_no_mencionado(self):
        cases = [
            NumericCase(
                concept="edad",
                expected_patterns=["setenta años"],
                incorrect_patterns=["sesenta años"],
            )
        ]
        result = evaluate_numeric("Sin mención de la edad.", cases)
        assert result.passed == 0
        assert result.failed == 0
        assert result.details[0].result == "not_detected"


class TestMissingInformationCompleteness:
    def test_tema_esperado_presente(self):
        content = {"items": [{"topic": "otalgia", "suggested_question": "¿Dolor de oído?"}]}
        cases = [FactCase(description="otalgia", patterns=["otalgia", "dolor de oído"])]
        result = evaluate_missing_information_completeness(content, cases)
        assert result.expected_present == 1

    def test_tema_esperado_ausente(self):
        content = {"items": []}
        cases = [FactCase(description="otalgia", patterns=["otalgia"])]
        result = evaluate_missing_information_completeness(content, cases)
        assert result.expected_present == 0
        assert result.expected_missing == 1


class TestEvidenceCoverage:
    def test_sin_source_excerpt_declarado_es_null(self):
        # SUMMARY/MISSING_INFORMATION/PATIENT_SUMMARY no declaran
        # source_excerpt en su schema hoy — ver encargo Fase 6.2, alcance.
        assert evaluate_evidence_coverage({"text": "resumen"}, None) is None

    def test_con_source_excerpt_declarado_calcula_cobertura(self):
        content = {"items": [{"topic": "a", "source_excerpt": "algo del transcript"}]}
        source_map = {"items[0]": {"field": "items[0]", "excerpt": "algo del transcript"}}
        result = evaluate_evidence_coverage(content, source_map)
        assert result is not None
        assert result.fields_declaring_evidence == 1
        assert result.fields_with_valid_evidence == 1
        assert result.coverage == 1.0
