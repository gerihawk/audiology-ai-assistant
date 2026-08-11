"""source_excerpt debe ser una ventana real alrededor del match, nunca un
prefijo decorativo del transcript — ver docs/fase-6-rfc.md §4.4."""

from __future__ import annotations

import uuid

from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_clinical_flags_generator import MockClinicalFlagsGenerator

_CONTEXT = SessionContext(clinical_session_id=uuid.uuid4())


async def test_source_excerpt_is_a_window_around_the_match_not_a_prefix():
    padding = "relleno " * 40  # empuja el match bien lejos de transcript[:200]
    transcript = f"{padding}el paciente refiere otalgia intensa desde ayer."
    generator = MockClinicalFlagsGenerator()

    flags = await generator.generate(transcript, context=_CONTEXT)

    otalgia_flag = next(f for f in flags if f.category == "otalgia")
    assert "otalgia" in otalgia_flag.source_excerpt.lower()
    assert otalgia_flag.source_excerpt != transcript[:200]


async def test_source_excerpt_covers_both_keywords_of_a_multi_word_rule():
    transcript = (
        "Consulta de seguimiento. El paciente comenta acúfenos en el oído "
        "izquierdo desde hace dos semanas, sin otros síntomas asociados."
    )
    generator = MockClinicalFlagsGenerator()

    flags = await generator.generate(transcript, context=_CONTEXT)

    tinnitus_flag = next(f for f in flags if f.category == "tinnitus_unilateral")
    assert "acúfenos" in tinnitus_flag.source_excerpt.lower()
    assert "izquierdo" in tinnitus_flag.source_excerpt.lower()


async def test_no_flags_when_no_keywords_match():
    generator = MockClinicalFlagsGenerator()

    flags = await generator.generate("Consulta rutinaria sin incidencias.", context=_CONTEXT)

    assert flags == []
