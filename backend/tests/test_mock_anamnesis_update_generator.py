"""Tests de `MockAnamnesisUpdateGenerator` — Hito 6.5.2, RFC técnico de
6.5 §4-§11. Deterministas, sin LLM, sin red: encadenan el resultado real
del Mock con las primitivas de dominio de 6.5.1
(`validate_update_batch`/`verify_update_grounding`/`materialize_anamnesis`)
para demostrar que el Mock produce algo que el dominio realmente acepta —
nunca duplican esa lógica de validación aquí."""

from __future__ import annotations

import uuid

from app.ai_pipeline.domain.anamnesis_update import (
    materialize_anamnesis,
    validate_update_batch,
    verify_update_grounding,
)
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.schemas import validate_content_schema
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS, AnamnesisFieldStatus
from app.integrations.domain.anamnesis_update_generator import AnamnesisUpdateReason
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_anamnesis_update_generator import MockAnamnesisUpdateGenerator
from tests.clinical_fixtures import (
    AMBIGUOUS_REFERENCE_TRANSCRIPT,
    CORRECTED_VALUE_TRANSCRIPT,
    EXPLICIT_CORRECTION_TRANSCRIPT,
    FIRST_VISIT_TRANSCRIPT,
    LONGITUDINAL_ONLY_PHRASE,
    UNMARKED_CONTRADICTION_TRANSCRIPT,
    UNMARKED_POSITIVE_VERTIGO_TRANSCRIPT,
)


def _field(value: str, status: AnamnesisFieldStatus, source_excerpt: str | None = None) -> dict:
    return {"value": value, "status": status.value, "source_excerpt": source_excerpt}


def _baseline(**field_overrides: dict) -> dict:
    content = {
        name: {
            "value": "",
            "status": AnamnesisFieldStatus.NO_PREGUNTADO.value,
            "source_excerpt": None,
        }
        for name in ANAMNESIS_FIELDS
    }
    content.update(field_overrides)
    return content


#: Baseline reutilizado por los casos que usan `FIRST_VISIT_TRANSCRIPT`
#: (contiene "acúfenos" Y "niega vértigo"): fija `vertigo_o_inestabilidad`
#: en un estado no-laguna sin marcador de corrección presente en ese
#: transcript, para aislar el trigger de `tinnitus` bajo test — sin esto,
#: "niega vértigo" también dispararía un `fills_gap` porque el valor por
#: defecto de todo campo no mencionado es `no_preguntado` (una laguna).
def _first_visit_baseline(**tinnitus_override: dict) -> dict:
    return _baseline(
        vertigo_o_inestabilidad=_field(
            "El paciente ya había negado vértigo en una visita previa.",
            AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
            source_excerpt="no refiere vértigo en la valoración inicial",
        ),
        **tinnitus_override,
    )


async def _generate(transcript: str, baseline: dict, *, session_type: str | None = None):
    context = SessionContext(uuid.uuid4(), session_type=session_type)
    return await MockAnamnesisUpdateGenerator().generate(transcript, baseline, context=context)


# ============================================================
# A/B. fills_gap
# ============================================================


class TestFillsGap:
    async def test_no_preguntado_with_new_evidence_yields_one_fills_gap_update(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        assert len(result.updates) == 1
        update = result.updates[0]
        assert update.field_name == "tinnitus"
        assert update.reason == AnamnesisUpdateReason.FILLS_GAP
        assert update.proposed_status == AnamnesisFieldStatus.INFORMADO

    async def test_no_determinado_with_new_evidence_yields_one_fills_gap_update(self):
        baseline = _first_visit_baseline(
            tinnitus=_field("Se mencionó algo poco claro.", AnamnesisFieldStatus.NO_DETERMINADO)
        )
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        assert len(result.updates) == 1
        assert result.updates[0].reason == AnamnesisUpdateReason.FILLS_GAP


# ============================================================
# C/D. explicit_correction
# ============================================================


class TestExplicitCorrection:
    async def test_informado_with_explicit_marker_yields_explicit_correction_new_value(self):
        baseline = _baseline(
            otalgia=_field(
                "Dolor leve en oído izquierdo.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="dolor leve en el oído",
            )
        )
        result = await _generate(CORRECTED_VALUE_TRANSCRIPT, baseline)

        assert len(result.updates) == 1
        update = result.updates[0]
        assert update.field_name == "otalgia"
        assert update.reason == AnamnesisUpdateReason.EXPLICIT_CORRECTION
        assert update.proposed_status == AnamnesisFieldStatus.INFORMADO
        assert update.proposed_value != update.previous_value

    async def test_negado_explicitamente_with_explicit_marker_yields_explicit_correction(self):
        baseline = _baseline(
            tinnitus=_field(
                "El paciente niega pitidos.",
                AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                source_excerpt="no ha notado pitidos hasta ahora",
            )
        )
        result = await _generate(EXPLICIT_CORRECTION_TRANSCRIPT, baseline)

        assert len(result.updates) == 1
        update = result.updates[0]
        assert update.field_name == "tinnitus"
        assert update.reason == AnamnesisUpdateReason.EXPLICIT_CORRECTION
        assert update.proposed_status == AnamnesisFieldStatus.INFORMADO


# ============================================================
# E/F/G/H. sin marcador explícito -> nunca se propone un cambio
# ============================================================


class TestNoUpdateWithoutExplicitMarker:
    async def test_informado_contradicted_without_marker_yields_no_update(self):
        baseline = _baseline(
            tinnitus=_field(
                "Pitido intenso en oído izquierdo desde hace un año.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="pitido intenso en el oído izquierdo",
            )
        )
        result = await _generate(UNMARKED_CONTRADICTION_TRANSCRIPT, baseline)
        assert result.updates == []

    async def test_negado_contradicted_without_marker_yields_no_update(self):
        baseline = _baseline(
            vertigo_o_inestabilidad=_field(
                "El paciente niega vértigo.",
                AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                source_excerpt="no refiere vértigo",
            )
        )
        result = await _generate(UNMARKED_POSITIVE_VERTIGO_TRANSCRIPT, baseline)
        assert result.updates == []

    async def test_informado_with_compatible_information_yields_no_update(self):
        baseline = _baseline(
            tinnitus=_field(
                "Acúfenos leves ya documentados en visita anterior.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="acúfenos leves",
            ),
            vertigo_o_inestabilidad=_field(
                "El paciente refiere cierto vértigo ocasional.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="algo de vértigo ocasional",
            ),
        )
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)
        assert result.updates == []

    async def test_negado_reaffirmed_yields_no_update(self):
        baseline = _baseline(
            vertigo_o_inestabilidad=_field(
                "El paciente ya negó vértigo antes.",
                AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                source_excerpt="no refiere vértigo",
            ),
            tinnitus=_field(
                "Acúfenos ya documentados.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="acúfenos",
            ),
        )
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)
        assert result.updates == []


# ============================================================
# I. transcript sin nada actualizable
# ============================================================


class TestNoUpdatableData:
    async def test_transcript_without_recognized_keywords_yields_no_updates(self):
        result = await _generate(AMBIGUOUS_REFERENCE_TRANSCRIPT, _baseline())
        assert result.updates == []


# ============================================================
# J/K. previous_value/status reales + source_excerpt literal del
# transcript actual, nunca del baseline
# ============================================================


class TestUpdateFieldsReflectRealBaselineAndCurrentTranscript:
    async def test_previous_value_and_status_match_the_real_baseline(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        update = result.updates[0]
        assert update.previous_value == baseline["tinnitus"]["value"]
        assert update.previous_status.value == baseline["tinnitus"]["status"]

    async def test_source_excerpt_appears_literally_in_current_transcript(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        assert result.updates[0].source_excerpt in FIRST_VISIT_TRANSCRIPT

    async def test_source_excerpt_never_originates_from_previous_anamnesis(self):
        """El baseline contiene `LONGITUDINAL_ONLY_PHRASE` en un campo —
        frase deliberadamente ausente de todo transcript de
        `clinical_fixtures.py`. Si el Mock alguna vez copiara el excerpt
        del baseline en vez de recortarlo del transcript actual, esta
        frase aparecería en el resultado."""
        baseline = _first_visit_baseline(
            tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO),
            exposicion_ruido=_field(
                "Exposición a ruido documentada.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt=LONGITUDINAL_ONLY_PHRASE,
            ),
        )
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        assert result.updates  # precondición: sí se propuso algo
        for update in result.updates:
            assert LONGITUDINAL_ONLY_PHRASE not in update.source_excerpt

    async def test_result_passes_verify_update_grounding(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        grounding = verify_update_grounding(result.updates, FIRST_VISIT_TRANSCRIPT)
        assert grounding.ok is True


# ============================================================
# L/M/N. Integración real con las primitivas de dominio de 6.5.1
# ============================================================


class TestIntegrationWithDomainPrimitives:
    async def test_fills_gap_output_satisfies_validate_update_batch(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        validate_update_batch(result.updates)  # no debe lanzar

    async def test_explicit_correction_output_satisfies_validate_update_batch(self):
        baseline = _baseline(
            tinnitus=_field(
                "El paciente niega pitidos.",
                AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                source_excerpt="no ha notado pitidos hasta ahora",
            )
        )
        result = await _generate(EXPLICIT_CORRECTION_TRANSCRIPT, baseline)

        validate_update_batch(result.updates)

    async def test_output_grounds_only_the_modified_field(self):
        baseline = _baseline(
            otalgia=_field(
                "Dolor leve en oído izquierdo.",
                AnamnesisFieldStatus.INFORMADO,
                source_excerpt="dolor leve en el oído",
            )
        )
        result = await _generate(CORRECTED_VALUE_TRANSCRIPT, baseline)

        grounding = verify_update_grounding(result.updates, CORRECTED_VALUE_TRANSCRIPT)
        assert grounding.ok is True
        assert set(grounding.source_map.keys()) == {"otalgia"}

    async def test_materialize_anamnesis_produces_a_schema_valid_document(self):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))
        result = await _generate(FIRST_VISIT_TRANSCRIPT, baseline)

        validate_update_batch(result.updates)
        materialized = materialize_anamnesis(baseline, result.updates)

        schema_result = validate_content_schema(AIArtifactType.ANAMNESIS, materialized)
        assert schema_result.valid, schema_result.errors
        assert materialized["tinnitus"]["status"] == "informado"
        # el campo suprimido deliberadamente (sin marcador) no se altera:
        assert materialized["vertigo_o_inestabilidad"] == baseline["vertigo_o_inestabilidad"]


# ============================================================
# O. Invariancia de session_type
# ============================================================


class TestSessionTypeInvariance:
    async def test_same_transcript_and_baseline_yield_same_updates_regardless_of_session_type(
        self,
    ):
        baseline = _first_visit_baseline(tinnitus=_field("", AnamnesisFieldStatus.NO_PREGUNTADO))

        with_type = await _generate(FIRST_VISIT_TRANSCRIPT, baseline, session_type="follow_up")
        without_type = await _generate(FIRST_VISIT_TRANSCRIPT, baseline, session_type=None)

        assert with_type.updates == without_type.updates
