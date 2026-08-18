"""Tests de `ruleset_disclaimer_for()` (app/ai_pipeline/domain/entities.py) —
única fuente de verdad de docs/clinical-safety.md §7 compartida por
`ai_pipeline/api/schemas.py` y `clinical_record/api/schemas.py`."""

from __future__ import annotations

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, ruleset_disclaimer_for
from app.core.messages.es import RULESET_DISCLAIMER

_NON_CLINICAL_FLAGS_TYPES = [t for t in AIArtifactType if t != AIArtifactType.CLINICAL_FLAGS]


def test_clinical_flags_lleva_el_ruleset_disclaimer():
    assert ruleset_disclaimer_for(AIArtifactType.CLINICAL_FLAGS) == RULESET_DISCLAIMER


@pytest.mark.parametrize("artifact_type", _NON_CLINICAL_FLAGS_TYPES)
def test_ningun_otro_tipo_lleva_ruleset_disclaimer(artifact_type: AIArtifactType):
    assert ruleset_disclaimer_for(artifact_type) is None
