"""Tests de `SafetyValidator` (app/ai_pipeline/domain/safety.py) — ver
docs/fase-6-rfc.md §5.2 y §14 del encargo de la Fase 6.1."""

from __future__ import annotations

import pytest

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


def test_typo_de_tilde_no_es_una_via_de_escape():
    content = {"text": "El paciente tíene acúfenos."}  # tílde extra deliberada (typo)
    # Actualizado en el cierre del hallazgo bloqueante del red team
    # (docs/security/red-team-app-2026-09-22.md §A1, 2026-09-22): este test
    # antes esperaba valid=True, con el argumento de que "tíene" (typo) no
    # es literalmente "tiene". Ese razonamiento ya no se sostiene: "El
    # paciente tíene acúfenos" — typo aparte — es exactamente el tipo de
    # afirmación asertiva que docs/clinical-safety.md §3 prohíbe. El test
    # viejo solo pasaba porque el validador anterior era demasiado estrecho
    # para verlo (comparaba contra 3 strings literales), no porque este
    # contenido fuera legítimo. `_strip_accents` (necesario para cerrar el
    # bypass real de "diagnostico confirmado" sin tilde) no puede distinguir
    # "tilde omitida" de "tilde puesta en la letra equivocada" — ambas
    # colapsan al mismo texto normalizado, y aquí eso es lo correcto: un
    # typo sobre una frase prohibida sigue siendo la misma frase prohibida.
    assert validate_safety(content).valid is False


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


# --- Red team Fase 0 (2026-09-22): bypass del SafetyValidator ------------
#
# Hallazgo bloqueante del informe docs/security/red-team-app-2026-09-22.md
# §A1: FORBIDDEN_CLINICAL_LANGUAGE solo compara contra 3 strings literales,
# pero docs/clinical-safety.md §3 define el lenguaje prohibido como un
# CONCEPTO amplio ("cualquier formulación que presente una inferencia de la
# IA como hecho clínico establecido"), no una lista cerrada de frases. Estos
# 15 casos reproducen el bypass con sinónimos, orden de palabras distinto,
# tildes retiradas e inglés — ninguno reutiliza literalmente ninguna de las
# 3 frases de FORBIDDEN_CLINICAL_LANGUAGE tal cual.
#
# Se espera que ESTE TEST FALLE contra la implementación actual (confirma
# el hallazgo). Debe pasar íntegro una vez se implemente el arreglo
# acordado — no se ha tocado safety.py todavía.
@pytest.mark.parametrize(
    "descripcion,texto",
    [
        (
            "sinónimo de 'tiene': 'presenta'",
            "El paciente presenta hipoacusia neurosensorial bilateral.",
        ),
        (
            "sinónimo de 'tiene': 'sufre de'",
            "El paciente sufre de acúfenos crónicos desde hace un año.",
        ),
        (
            "orden de palabras invertido de 'el paciente tiene'",
            "Tiene el paciente una pérdida auditiva significativa.",
        ),
        (
            "palabras insertadas rompen el substring contiguo 'el paciente tiene'",
            "El paciente, según el análisis del sistema, tiene una pérdida auditiva.",
        ),
        (
            "'diagnóstico confirmado' sin tildes",
            "Diagnostico confirmado de perdida auditiva bilateral.",
        ),
        (
            "sinónimo/orden distinto de 'diagnóstico confirmado'",
            "Se confirma el diagnóstico de hipoacusia bilateral.",
        ),
        (
            "paráfrasis de 'diagnóstico confirmado'",
            "El diagnóstico ha sido confirmado por el sistema tras el análisis.",
        ),
        (
            "palabra insertada rompe el substring contiguo 'diagnóstico confirmado'",
            "Diagnóstico ya confirmado tras la valoración automática.",
        ),
        (
            "paráfrasis de 'tratamiento recomendado automáticamente'",
            "Se recomienda tratamiento de forma automática según el protocolo.",
        ),
        (
            "paráfrasis distinta de 'tratamiento recomendado automáticamente'",
            "El sistema asigna tratamiento automáticamente sin revisión humana.",
        ),
        (
            "palabras insertadas rompen el substring de 'tratamiento recomendado automáticamente'",
            "Tratamiento recomendado por el sistema de forma totalmente automática.",
        ),
        (
            "hecho clínico presentado como establecido, sin usar ninguna de las 3 frases",
            "Hipoacusia neurosensorial bilateral confirmada mediante audiometría.",
        ),
        (
            "catch-all de §3: inferencia de la IA presentada como hecho clínico",
            "Queda establecido que el paciente padece acúfenos crónicos.",
        ),
        (
            "equivalente en inglés de 'el paciente tiene'",
            "The patient has bilateral sensorineural hearing loss.",
        ),
        (
            "equivalente en inglés de 'diagnóstico confirmado'",
            "Diagnosis confirmed: moderate sensorineural hearing loss.",
        ),
    ],
)
def test_bypass_reformulaciones_no_detectadas_por_lista_literal(descripcion, texto):
    content = {"summary": texto}
    result = validate_safety(content)
    assert result.valid is False, (
        f"Bypass confirmado ({descripcion}): '{texto}' no fue detectado como "
        "lenguaje clínico prohibido pese a violar docs/clinical-safety.md §3."
    )
