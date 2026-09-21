"""Tests de las métricas deterministas nuevas del benchmark de generación
— Fase 6.2. Terminología/negación/lateralidad ya están cubiertas por los
tests del benchmark ASR (reutilizadas tal cual, sin duplicar aquí)."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType
from benchmark.generation.case_metadata import FactCase, NumericCase
from benchmark.generation.field_criticality import (
    ANAMNESIS_CRITICAL_FIELDS,
    SESSION_NOTES_CRITICAL_BLOCKS,
)
from benchmark.generation.metrics import (
    evaluate_evidence_coverage,
    evaluate_field_status_match,
    evaluate_forbidden_facts,
    evaluate_missing_information_completeness,
    evaluate_numeric,
    evaluate_required_facts,
    flatten_content_text,
    flatten_missing_information_topics,
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


class TestFlattenMissingInformationTopics:
    def test_solo_extrae_topic_nunca_suggested_question(self):
        content = {
            "items": [
                {"topic": "Detalles de mareo", "suggested_question": "¿Ha tenido vértigo?"},
                {"topic": "Historial previo", "suggested_question": "¿Acúfenos antes?"},
            ]
        }
        result = flatten_missing_information_topics(content)
        assert "vértigo" not in result.lower()
        assert "acúfenos" not in result.lower()
        assert "Detalles de mareo" in result
        assert "Historial previo" in result

    def test_estructura_invalida_no_lanza(self):
        assert flatten_missing_information_topics({}) == ""
        assert flatten_missing_information_topics({"items": None}) == ""
        assert flatten_missing_information_topics({"items": "no es una lista"}) == ""
        assert flatten_missing_information_topics({"items": [{"topic": None}]}) == ""
        assert flatten_missing_information_topics(None) == ""


class TestMissingInformationForbiddenTopicScoping:
    """Separación de responsabilidades acordada en el diagnóstico
    post-mortem 2026-08-12: los falsos positivos de `forbidden_facts`
    (grupo B — temas ya cubiertos) se evalúan EXCLUSIVAMENTE sobre
    `items[].topic`; `evaluate_missing_information_completeness` (recall)
    sigue evaluando `topic + suggested_question` sin cambios, porque
    responde a una pregunta distinta."""

    _forbidden = [
        FactCase(description="vértigo ya cubierto", patterns=["vértigo"]),
        FactCase(description="acúfenos ya cubiertos", patterns=["acúfenos"]),
        FactCase(description="exposición laboral ya cubierta", patterns=["exposición laboral"]),
    ]

    def test_a_forbidden_en_topic_se_detecta(self):
        content = {
            "items": [{"topic": "[NO EXPLORADO] vértigo", "suggested_question": "cualquier texto"}]
        }
        haystack = flatten_missing_information_topics(content)
        result = evaluate_forbidden_facts(haystack, self._forbidden)
        assert result.forbidden_found > 0

    def test_b_mencion_en_suggested_question_no_dispara(self):
        content = {
            "items": [
                {
                    "topic": "[PARCIAL] equilibrio reciente",
                    "suggested_question": (
                        "Aunque no ha tenido vértigo, ¿en el último año ha tenido "
                        "inestabilidad...?"
                    ),
                }
            ]
        }
        haystack = flatten_missing_information_topics(content)
        result = evaluate_forbidden_facts(haystack, self._forbidden)
        assert result.forbidden_found == 0

    def test_c_mencion_de_acufenos_solo_en_pregunta_no_dispara(self):
        content = {
            "items": [
                {
                    "topic": "[PARCIAL] historial de consultas previas",
                    "suggested_question": (
                        "¿Se ha hecho alguna audiometría antes o ha consultado "
                        "previamente por la audición o los acúfenos?"
                    ),
                }
            ]
        }
        haystack = flatten_missing_information_topics(content)
        result = evaluate_forbidden_facts(haystack, self._forbidden)
        assert result.forbidden_found == 0

    def test_d_forbidden_genuino_en_topic_sigue_siendo_detectable(self):
        # El fix no debe ocultar un topic extra real: si el patrón aparece
        # en el propio topic (no solo en la pregunta), sigue siendo un
        # candidato a falso positivo genuino.
        content = {
            "items": [
                {
                    "topic": "Uso de protección auditiva y exposición laboral",
                    "suggested_question": "¿Con qué frecuencia usaba protección?",
                }
            ]
        }
        haystack = flatten_missing_information_topics(content)
        result = evaluate_forbidden_facts(haystack, self._forbidden)
        assert result.forbidden_found > 0

    def test_e_expected_topic_presente_solo_en_suggested_question_cuenta_para_recall(self):
        # evaluate_missing_information_completeness NO cambia: sigue
        # buscando en topic + suggested_question combinados.
        content = {
            "items": [
                {
                    "topic": "[PARCIAL] equilibrio reciente",
                    "suggested_question": "¿Ha tenido vértigo en el último año?",
                }
            ]
        }
        expected = [FactCase(description="vértigo", patterns=["vértigo"])]
        result = evaluate_missing_information_completeness(content, expected)
        assert result.expected_present == 1
        assert result.expected_missing == 0

    def test_f_expected_topic_presente_en_topic_cuenta_para_recall(self):
        content = {"items": [{"topic": "Vértigo no explorado", "suggested_question": "n/a"}]}
        expected = [FactCase(description="vértigo", patterns=["vértigo"])]
        result = evaluate_missing_information_completeness(content, expected)
        assert result.expected_present == 1

    def test_g_expected_topic_ausente_en_ambos_campos_es_omitido(self):
        content = {"items": [{"topic": "Otro tema", "suggested_question": "otra pregunta"}]}
        expected = [FactCase(description="vértigo", patterns=["vértigo"])]
        result = evaluate_missing_information_completeness(content, expected)
        assert result.expected_present == 0
        assert result.expected_missing == 1

    def test_i_summary_sigue_usando_flatten_content_text_sin_cambios(self):
        # SUMMARY/PATIENT_SUMMARY no tienen items[] — el scoping nuevo es
        # exclusivo de MISSING_INFORMATION (aplicado en runner.py, no aquí)
        # — esta prueba confirma que flatten_content_text (el mecanismo que
        # SUMMARY/PATIENT_SUMMARY siguen usando) es indiferente a la nueva
        # función y sigue aplanando todo el contenido, sin scoping.
        content = {"text": "Diagnóstico confirmado de hipoacusia neurosensorial."}
        forbidden = [FactCase(description="diagnóstico", patterns=["diagnóstico confirmado"])]
        result = evaluate_forbidden_facts(flatten_content_text(content), forbidden)
        assert result.forbidden_found == 1


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


def _anamnesis_field(status: str, source_excerpt: str | None = "cita literal") -> dict:
    return {"value": "algo", "status": status, "source_excerpt": source_excerpt}


class TestFieldStatusMatchAnamnesis:
    """hito 6.4.4 — docs/fase-6-4-4-anamnesis-benchmark-rfc.md §2. `tinnitus`
    es crítico y `expectativas` no crítico según
    benchmark.generation.field_criticality (confirmado por Gerard)."""

    def test_status_coincide_es_match(self):
        reference = {"tinnitus": _anamnesis_field("informado")}
        generated = {"tinnitus": _anamnesis_field("informado")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert len(report.details) == 1
        assert report.details[0].outcome == "match"
        assert report.critical_escalations == 0
        assert report.critical_downgrades == 0

    def test_fabricar_status_sobre_campo_critico_es_escalation_critica(self):
        # Referencia: nunca se preguntó. Modelo: afirma que sí, con una cita
        # real pero irrelevante para ese campo.
        reference = {"tinnitus": _anamnesis_field("no_preguntado", source_excerpt=None)}
        generated = {"tinnitus": _anamnesis_field("informado")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_escalation"
        assert report.critical_escalations == 1
        assert report.noncritical_escalations == 0

    def test_omitir_status_sobre_campo_critico_es_downgrade_critico(self):
        # Referencia: el paciente sí reportó tinnitus. Modelo: lo omite.
        reference = {"tinnitus": _anamnesis_field("informado")}
        generated = {"tinnitus": _anamnesis_field("no_preguntado", source_excerpt=None)}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_downgrade"
        assert report.critical_downgrades == 1
        assert report.noncritical_downgrades == 0

    def test_mismo_error_sobre_campo_no_critico_no_cuenta_como_critico(self):
        reference = {"expectativas": _anamnesis_field("no_determinado", source_excerpt=None)}
        generated = {"expectativas": _anamnesis_field("informado")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_escalation"
        assert report.critical_escalations == 0
        assert report.noncritical_escalations == 1

    def test_informado_vs_negado_explicitamente_es_mismatch_no_escalation_ni_downgrade(self):
        reference = {"tinnitus": _anamnesis_field("informado")}
        generated = {"tinnitus": _anamnesis_field("negado_explicitamente")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_mismatch"
        assert report.mismatches == 1
        assert report.critical_escalations == 0
        assert report.critical_downgrades == 0

    def test_solo_compara_campos_presentes_en_ambos_lados(self):
        reference = {"tinnitus": _anamnesis_field("informado")}
        generated = {}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.ANAMNESIS,
            generated_content=generated,
            reference_content=reference,
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is not None
        assert report.details == []

    def test_artifact_type_sin_soporte_devuelve_none(self):
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.SUMMARY,
            generated_content={"text": "x"},
            reference_content={"text": "x"},
            critical_fields=ANAMNESIS_CRITICAL_FIELDS,
        )
        assert report is None


def _session_notes_block(text: str) -> dict:
    return {"text": text, "source_excerpt": "cita literal" if text else None}


class TestFieldStatusMatchSessionNotes:
    """`device_adjustments` es crítico, `next_steps` no — mismo status
    derivado (`reported`/`not_reported`) que ANAMNESIS agrupa igual en
    evidencia/sin-evidencia (SessionNotesBlock no tiene enum de status)."""

    def test_texto_vacio_en_ambos_lados_es_match(self):
        reference = {"device_adjustments": _session_notes_block("")}
        generated = {"device_adjustments": _session_notes_block("")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.SESSION_NOTES,
            generated_content=generated,
            reference_content=reference,
            critical_fields=SESSION_NOTES_CRITICAL_BLOCKS,
        )
        assert report is not None
        assert report.details[0].outcome == "match"

    def test_omitir_bloque_critico_reportado_es_downgrade_critico(self):
        reference = {"device_adjustments": _session_notes_block("ajuste de ganancia en agudos")}
        generated = {"device_adjustments": _session_notes_block("")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.SESSION_NOTES,
            generated_content=generated,
            reference_content=reference,
            critical_fields=SESSION_NOTES_CRITICAL_BLOCKS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_downgrade"
        assert report.critical_downgrades == 1

    def test_fabricar_bloque_no_critico_es_escalation_no_critica(self):
        reference = {"next_steps": _session_notes_block("")}
        generated = {"next_steps": _session_notes_block("revisión en 3 meses")}
        report = evaluate_field_status_match(
            artifact_type=AIArtifactType.SESSION_NOTES,
            generated_content=generated,
            reference_content=reference,
            critical_fields=SESSION_NOTES_CRITICAL_BLOCKS,
        )
        assert report is not None
        assert report.details[0].outcome == "status_escalation"
        assert report.critical_escalations == 0
        assert report.noncritical_escalations == 1
