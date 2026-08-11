"""Tests de `GroundingValidator` (app/ai_pipeline/domain/grounding.py) —
primitiva `(excerpt, transcript) -> resultado`, determinista, sin LLM. Ver
docs/fase-6-rfc.md §5.3 y §15 del encargo de la Fase 6.1.

Los casos ligados al estado de un campo de anamnesis (informado/
negado_explicitamente/no_preguntado/no_determinado) y a la política de
degradación/rechazo se cubren en test_ai_pipeline_validation_pipeline.py,
porque esa lógica pertenece a la composición por artefacto, no a esta
primitiva genérica.
"""

from __future__ import annotations

from app.ai_pipeline.domain.grounding import verify_excerpt

_TRANSCRIPT = (
    "El paciente refiere acúfenos en el oído izquierdo desde hace tres meses. "
    "Niega vértigo o inestabilidad. ¿Ha notado otorrea? No, en absoluto."
)


def test_excerpt_exacto_se_verifica_con_offsets_originales():
    excerpt = "acúfenos en el oído izquierdo"
    result = verify_excerpt(excerpt, _TRANSCRIPT)
    assert result.grounded is True
    assert _TRANSCRIPT[result.original_start : result.original_end] == excerpt


def test_normalizacion_de_mayusculas():
    result = verify_excerpt("ACÚFENOS EN EL OÍDO IZQUIERDO", _TRANSCRIPT)
    assert result.grounded is True


def test_normalizacion_de_puntuacion():
    result = verify_excerpt("Ha notado otorrea", _TRANSCRIPT)
    assert result.grounded is True


def test_normalizacion_de_tildes_no_elimina_la_tilde_pero_iguala_variantes():
    # La cita real lleva tilde; buscarla con la misma tilde debe verificarse.
    result = verify_excerpt("vértigo o inestabilidad", _TRANSCRIPT)
    assert result.grounded is True


def test_normalizacion_de_espacios_colapsados():
    result = verify_excerpt("acúfenos   en el    oído izquierdo", _TRANSCRIPT)
    assert result.grounded is True


def test_excerpt_inexistente_no_se_verifica():
    result = verify_excerpt("pérdida auditiva bilateral severa", _TRANSCRIPT)
    assert result.grounded is False
    assert result.original_start is None
    assert result.original_end is None


def test_transcript_vacio_nunca_verifica_nada():
    result = verify_excerpt("acúfenos", "")
    assert result.grounded is False


def test_source_excerpt_vacio_nunca_es_evidencia_valida():
    assert verify_excerpt("", _TRANSCRIPT).grounded is False
    assert verify_excerpt("   ", _TRANSCRIPT).grounded is False


def test_excerpt_de_solo_normalizacion_no_reporta_offsets_originales():
    result = verify_excerpt("ACÚFENOS EN EL OÍDO IZQUIERDO", _TRANSCRIPT)
    assert result.grounded is True
    assert result.original_start is None
    assert result.original_end is None
