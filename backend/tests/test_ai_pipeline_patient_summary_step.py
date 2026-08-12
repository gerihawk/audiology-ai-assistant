"""Tests de `PatientSummaryStep` (Fase 6.3.1) — sin BD, sin proveedor real.

Cubre la dependencia blanda con `SUMMARY` (RFC §4.3: "cuando esté
disponible en la ejecución") y el paso de usage real del generator hacia
`PipelineStepOutcome` — ver docs/fase-6-rfc.md §4.3 y §6.3.
"""

from __future__ import annotations

import uuid

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.patient_summary_step import PatientSummaryStep
from app.integrations.domain.patient_summary_generator import PatientSummaryDraft
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_token_counter import MockTokenCounter

_TRANSCRIPT = "El paciente refiere acúfenos en el oído izquierdo desde hace dos semanas."


class _FixedCostEstimator:
    def estimate(self, *, provider, model, input_tokens, output_tokens):
        from decimal import Decimal

        return Decimal("0")


class _SpyPatientSummaryGenerator:
    """Captura los argumentos recibidos y devuelve un `PatientSummaryDraft`
    fijo, con usage configurable."""

    def __init__(self, *, input_tokens=None, output_tokens=None) -> None:
        self.received_transcript: str | None = None
        self.received_summary_text: str | None = None
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    async def generate(self, transcript, summary_text, *, context):
        self.received_transcript = transcript
        self.received_summary_text = summary_text
        return PatientSummaryDraft(
            text="Explicación para el paciente.",
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )


def _context(**outputs_overrides) -> PipelineExecutionContext:
    context = PipelineExecutionContext(
        clinical_session_id=uuid.uuid4(),
        session_context=SessionContext(clinical_session_id=uuid.uuid4()),
    )
    context.outputs[AIArtifactType.TRANSCRIPT] = {"text": _TRANSCRIPT, "language": "es"}
    context.outputs.update(outputs_overrides)
    return context


def test_depends_on_solo_transcript():
    step = PatientSummaryStep(
        _SpyPatientSummaryGenerator(), MockTokenCounter(), _FixedCostEstimator()
    )
    assert step.depends_on() == frozenset({AIArtifactType.TRANSCRIPT})


async def test_usa_summary_cuando_esta_disponible_en_la_ejecucion():
    generator = _SpyPatientSummaryGenerator()
    step = PatientSummaryStep(generator, MockTokenCounter(), _FixedCostEstimator())
    context = _context(**{AIArtifactType.SUMMARY: {"text": "Resumen técnico de la consulta."}})

    outcome = await step.run(context)

    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert generator.received_transcript == _TRANSCRIPT
    assert generator.received_summary_text == "Resumen técnico de la consulta."


async def test_nunca_falla_si_summary_no_esta_disponible():
    generator = _SpyPatientSummaryGenerator()
    step = PatientSummaryStep(generator, MockTokenCounter(), _FixedCostEstimator())
    context = _context()  # sin AIArtifactType.SUMMARY en outputs

    outcome = await step.run(context)

    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert generator.received_summary_text == ""


async def test_contenido_resultante_cumple_el_esquema_de_patient_summary():
    step = PatientSummaryStep(
        _SpyPatientSummaryGenerator(), MockTokenCounter(), _FixedCostEstimator()
    )
    outcome = await step.run(_context())

    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert outcome.content == {"text": "Explicación para el paciente."}


async def test_usage_real_del_generator_se_propaga_al_outcome():
    generator = _SpyPatientSummaryGenerator(input_tokens=123, output_tokens=45)
    step = PatientSummaryStep(generator, MockTokenCounter(), _FixedCostEstimator())

    outcome = await step.run(_context())

    assert outcome.input_token_count == 123
    assert outcome.output_token_count == 45


async def test_sin_usage_real_cae_al_token_counter_heuristico():
    generator = _SpyPatientSummaryGenerator(input_tokens=None, output_tokens=None)
    step = PatientSummaryStep(generator, MockTokenCounter(), _FixedCostEstimator())

    outcome = await step.run(_context())

    # MockTokenCounter cuenta palabras — heurística, nunca None cuando no
    # hay usage real disponible.
    assert outcome.input_token_count == len(_TRANSCRIPT.split())
    assert outcome.output_token_count == len(["Explicación", "para", "el", "paciente."])
