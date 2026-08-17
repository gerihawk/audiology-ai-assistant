"""Tests de `MockAnamnesisGenerator` — Fase 6.4.2: produce `source_excerpt`
reales (ventana literal del transcript), nunca decorativos ni citas
inventadas para campos sin evidencia."""

from __future__ import annotations

import uuid

from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator

_TRANSCRIPT = (
    "El paciente refiere acúfenos en el oído izquierdo desde hace tres meses. "
    "Niega vértigo o sensación de inestabilidad."
)


async def _generate(transcript: str):
    context = SessionContext(uuid.uuid4())
    return await MockAnamnesisGenerator().generate(transcript, [], context=context)


async def test_informado_field_has_literal_excerpt_from_transcript():
    draft = await _generate(_TRANSCRIPT)
    field = draft.fields["tinnitus"]

    assert field.status == AnamnesisFieldStatus.INFORMADO
    assert field.source_excerpt is not None
    assert field.source_excerpt in _TRANSCRIPT  # cita literal, no decorativa


async def test_negado_explicitamente_field_has_literal_excerpt_from_transcript():
    draft = await _generate(_TRANSCRIPT)
    field = draft.fields["vertigo_o_inestabilidad"]

    assert field.status == AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE
    assert field.source_excerpt is not None
    assert field.source_excerpt in _TRANSCRIPT


async def test_no_preguntado_fields_have_no_source_excerpt():
    draft = await _generate(_TRANSCRIPT)
    untouched_field = draft.fields["cirugias"]

    assert untouched_field.status == AnamnesisFieldStatus.NO_PREGUNTADO
    assert untouched_field.source_excerpt is None


async def test_excerpt_is_not_the_full_transcript_but_a_real_window():
    """Nunca `transcript[:200]` decorativo — la ventana debe ser más
    corta que el transcript completo cuando este es suficientemente
    largo."""
    long_transcript = _TRANSCRIPT + " " + ("Relleno de contexto adicional. " * 20)
    draft = await _generate(long_transcript)
    field = draft.fields["tinnitus"]

    assert field.source_excerpt is not None
    assert len(field.source_excerpt) < len(long_transcript)
    assert "acúfenos" in field.source_excerpt.lower()
