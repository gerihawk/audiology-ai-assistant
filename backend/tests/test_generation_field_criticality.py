"""Sanity checks de la clasificación crítico/no-crítico del hito 6.4.4 —
docs/fase-6-4-4-anamnesis-benchmark-rfc.md §4, confirmada por Gerard el
2026-09-21. No valida el juicio clínico (eso es de Gerard, no del código),
solo que la clasificación referencia campos/bloques reales — un typo aquí
haría que un campo crítico real quedara silenciosamente fuera del gate."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS
from benchmark.generation.field_criticality import (
    ANAMNESIS_CRITICAL_FIELDS,
    CRITICAL_FIELDS_BY_ARTIFACT_TYPE,
    SESSION_NOTES_CRITICAL_BLOCKS,
)


def test_campos_criticos_de_anamnesis_son_campos_reales():
    assert set(ANAMNESIS_FIELDS) >= ANAMNESIS_CRITICAL_FIELDS
    assert len(ANAMNESIS_CRITICAL_FIELDS) == 10  # docs/fase-6-4-4-...-rfc.md §4


def test_bloques_criticos_de_session_notes_son_bloques_reales():
    assert set(SESSION_NOTES_BLOCKS) >= SESSION_NOTES_CRITICAL_BLOCKS
    assert len(SESSION_NOTES_CRITICAL_BLOCKS) == 2


def test_mapa_por_artifact_type_cubre_ambos_tipos():
    assert set(CRITICAL_FIELDS_BY_ARTIFACT_TYPE) == {
        AIArtifactType.ANAMNESIS,
        AIArtifactType.SESSION_NOTES,
    }
    assert CRITICAL_FIELDS_BY_ARTIFACT_TYPE[AIArtifactType.ANAMNESIS] is ANAMNESIS_CRITICAL_FIELDS
    assert (
        CRITICAL_FIELDS_BY_ARTIFACT_TYPE[AIArtifactType.SESSION_NOTES]
        is SESSION_NOTES_CRITICAL_BLOCKS
    )
