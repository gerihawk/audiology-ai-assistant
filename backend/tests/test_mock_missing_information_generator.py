"""Tests de `MockMissingInformationGenerator` — Fase 6.4.4: el fixture
devuelto depende exclusivamente del `target` recibido, nunca lo decide
el propio generador."""

from __future__ import annotations

import uuid

from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.missing_information_generator import MissingInformationTarget
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS
from app.integrations.mocks.mock_missing_information_generator import (
    MockMissingInformationGenerator,
)


async def _generate(target: MissingInformationTarget):
    context = SessionContext(uuid.uuid4())
    return await MockMissingInformationGenerator().generate(
        "resumen", [], target=target, context=context
    )


async def test_target_anamnesis_fields_usa_topics_de_los_20_campos():
    result = await _generate(MissingInformationTarget.ANAMNESIS_FIELDS)

    assert len(result.items) > 0
    for item in result.items:
        assert item.topic in ANAMNESIS_FIELDS
        assert item.topic not in SESSION_NOTES_BLOCKS


async def test_target_session_notes_blocks_usa_topics_de_los_4_bloques():
    result = await _generate(MissingInformationTarget.SESSION_NOTES_BLOCKS)

    assert len(result.items) > 0
    for item in result.items:
        assert item.topic in SESSION_NOTES_BLOCKS
        assert item.topic not in ANAMNESIS_FIELDS


async def test_es_deterministico_para_el_mismo_target():
    first = await _generate(MissingInformationTarget.ANAMNESIS_FIELDS)
    second = await _generate(MissingInformationTarget.ANAMNESIS_FIELDS)

    assert first.items == second.items


async def test_targets_distintos_producen_items_distintos():
    anamnesis_result = await _generate(MissingInformationTarget.ANAMNESIS_FIELDS)
    session_notes_result = await _generate(MissingInformationTarget.SESSION_NOTES_BLOCKS)

    anamnesis_topics = {item.topic for item in anamnesis_result.items}
    session_notes_topics = {item.topic for item in session_notes_result.items}
    assert anamnesis_topics.isdisjoint(session_notes_topics)
