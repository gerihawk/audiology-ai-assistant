"""Tests de `ClinicalFlagsStep` con `RealClinicalFlagsGenerator` (ampliación
2026-09-21, docs/clinical-safety.md §7) — sin BD, sin proveedor real.

El caso más importante de este fichero es la prueba de que el
`grounding_failed` de `validate_generated_content` realmente hace fallar
el step completo cuando el LLM cita algo que no está en la transcripción
— la garantía central de que este generador no puede "inventar" una señal
clínica sin evidencia real (ver `RealClinicalFlagsGenerator` y
docs/fase-6-rfc.md §5.3). El resto de la cadena (schema, evasiva, safety)
ya se cubre genéricamente en test_ai_pipeline_validation_pipeline.py para
`AIArtifactType.CLINICAL_FLAGS`, agnóstico de qué generador produjo el
contenido — no se duplica aquí.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.clinical_flags_step import ClinicalFlagsStep
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_token_counter import MockTokenCounter

_TRANSCRIPT = "El paciente refiere acúfenos en el oído izquierdo desde hace dos semanas."


class _FixedCostEstimator:
    def estimate(self, *, provider, model, input_tokens, output_tokens):
        return Decimal("0")


class _FakeClinicalFlagsGenerator:
    def __init__(self, flags: list[ClinicalFlagDraft]) -> None:
        self._flags = flags

    async def generate(self, transcript, *, context):
        return self._flags


def _context() -> PipelineExecutionContext:
    context = PipelineExecutionContext(
        clinical_session_id=uuid.uuid4(),
        session_context=SessionContext(clinical_session_id=uuid.uuid4()),
    )
    context.outputs[AIArtifactType.TRANSCRIPT] = {"text": _TRANSCRIPT, "language": "es"}
    return context


async def test_flag_con_cita_real_completa_el_step():
    flags = [
        ClinicalFlagDraft(
            category="tinnitus_unilateral",
            description="Señal que requiere valoración profesional.",
            source_excerpt="acúfenos en el oído izquierdo",
            ruleset_name="clinical_flags_llm_es_v1",
        )
    ]
    step = ClinicalFlagsStep(
        _FakeClinicalFlagsGenerator(flags),
        MockTokenCounter(),
        _FixedCostEstimator(),
        provider_name="anthropic",
        model_name="claude-opus-5",
    )

    outcome = await step.run(_context())

    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert outcome.content == {
        "flags": [
            {
                "category": "tinnitus_unilateral",
                "description": "Señal que requiere valoración profesional.",
                "source_excerpt": "acúfenos en el oído izquierdo",
                "ruleset_name": "clinical_flags_llm_es_v1",
            }
        ]
    }
    assert outcome.source_map is not None


async def test_flag_con_cita_inventada_falla_el_step_con_grounding_failed():
    """El caso de seguridad crítico: una `source_excerpt` que NO aparece en
    la transcripción real de la sesión nunca debe llegar a persistirse
    como un borrador clínico revisable — el step entero falla."""
    flags = [
        ClinicalFlagDraft(
            category="otalgia",
            description="Señal que requiere valoración profesional.",
            source_excerpt="el paciente dijo que le dolía muchísimo el pecho",
            ruleset_name="clinical_flags_llm_es_v1",
        )
    ]
    step = ClinicalFlagsStep(
        _FakeClinicalFlagsGenerator(flags),
        MockTokenCounter(),
        _FixedCostEstimator(),
        provider_name="anthropic",
        model_name="claude-opus-5",
    )

    outcome = await step.run(_context())

    assert outcome.status == AIGenerationRunStatus.FAILED
    assert outcome.failure_reason == "grounding_failed"
    assert outcome.content is None


async def test_prompt_template_id_y_version_se_propagan_al_outcome():
    template_id = uuid.uuid4()
    step = ClinicalFlagsStep(
        _FakeClinicalFlagsGenerator([]),
        MockTokenCounter(),
        _FixedCostEstimator(),
        provider_name="anthropic",
        model_name="claude-opus-5",
        prompt_template_id=template_id,
        prompt_template_version=1,
    )

    outcome = await step.run(_context())

    assert outcome.prompt_template_id == template_id
    assert outcome.prompt_template_version == 1


async def test_mock_generator_sin_plantilla_no_lleva_prompt_template_id():
    step = ClinicalFlagsStep(
        _FakeClinicalFlagsGenerator([]), MockTokenCounter(), _FixedCostEstimator()
    )

    outcome = await step.run(_context())

    assert outcome.status == AIGenerationRunStatus.COMPLETED
    assert outcome.prompt_template_id is None
    assert outcome.prompt_template_version is None
