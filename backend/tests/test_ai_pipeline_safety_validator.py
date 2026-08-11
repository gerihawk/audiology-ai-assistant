"""Tests de `SafetyValidator` (app/ai_pipeline/domain/safety.py) — ver
docs/fase-6-rfc.md §5.2 y §14 del encargo de la Fase 6.1."""

from __future__ import annotations

from app.ai_pipeline.domain.safety import FORBIDDEN_CLINICAL_LANGUAGE, validate_safety


def test_contenido_seguro_no_genera_violaciones():
    content = {"text": "Señal que requiere valoración profesional."}
    result = validate_safety(content)
    assert result.valid is True
    assert result.violations == ()


def test_lenguaje_prohibido_en_campo_anidado_se_detecta():
    content = {
        "fields": {"tinnitus": {"value": "El paciente tiene acúfenos.", "status": "informado"}}
    }
    result = validate_safety(content)
    assert result.valid is False
    assert result.violations[0].field == "fields.tinnitus.value"
    assert result.violations[0].rule == "el paciente tiene"


def test_varias_violaciones_en_distintos_campos_se_reportan_todas():
    content = {
        "a": "Diagnóstico confirmado de hipoacusia.",
        "flags": [{"description": "Tratamiento recomendado automáticamente."}],
    }
    result = validate_safety(content)
    assert result.valid is False
    assert len(result.violations) == 2
    assert {v.rule for v in result.violations} == {
        "diagnóstico confirmado",
        "tratamiento recomendado automáticamente",
    }


def test_coincidencia_case_insensitive():
    content = {"text": "DIAGNÓSTICO CONFIRMADO de pérdida auditiva."}
    assert validate_safety(content).valid is False


def test_coincidencia_con_variacion_de_espacios_y_puntuacion():
    content = {"text": "el   paciente,  tiene una posible señal."}
    assert validate_safety(content).valid is False


def test_unicode_espanol_no_rompe_la_comparacion():
    content = {"text": "El paciente tíene acúfenos."}  # tílde extra deliberada
    # La normalización compara tras NFC + minúsculas; "tíene" no es
    # exactamente "tiene", así que esto NO debe marcarse — evita falsos
    # positivos por errores de tipografía ajenos a la frase prohibida real.
    assert validate_safety(content).valid is True


def test_falso_positivo_razonable_frase_parcial_no_coincide():
    content = {"text": "El paciente refiere tener acúfenos desde hace tres meses."}
    assert validate_safety(content).valid is True


def test_salida_estructurada_incluye_regla_ubicacion_y_motivo():
    content = {"summary": "diagnóstico confirmado"}
    result = validate_safety(content)
    violation = result.violations[0]
    assert violation.rule in FORBIDDEN_CLINICAL_LANGUAGE
    assert violation.field == "summary"
    assert violation.reason


def test_violacion_no_incluye_el_texto_completo_del_campo():
    long_text = "diagnóstico confirmado " + "relleno clínico sensible " * 20
    content = {"text": long_text}
    result = validate_safety(content)
    violation = result.violations[0]
    assert long_text not in repr(violation)
    assert "relleno clínico sensible" not in repr(violation)
