"""Paso del pipeline: notas de sesión estructuradas (Fase 6.4.3, RFC
técnico de 6.4 §8).

`depends_on()` es únicamente `{TRANSCRIPT}` — a diferencia de
`AnamnesisStep`, no depende de `MISSING_INFORMATION` (RFC técnico §8: "no
depende de MISSING_INFORMATION", `SessionNotesStep` es paralelo a
`ClinicalFlagsStep`, no una continuación de la cadena de anamnesis).

`applies_to()` (RFC técnico §5, espejo exacto e inverso de
`AnamnesisStep.applies_to()`): `True` solo cuando SÍ existe una
`ANAMNESIS` aprobada de OTRA sesión del paciente — nunca cuando el
contexto no se ha cargado (a diferencia de `AnamnesisStep`, cuyo default
seguro es `True`; aquí el default seguro simétrico es `False`: sin
confirmación de que existe anamnesis previa, nunca se asume que
`SESSION_NOTES` es válido generarlo).

Separación evidencia actual / contexto longitudinal (RFC técnico §7):
`previous_anamnesis_context` solo llega al `SessionNotesGenerator` para
ayudar a interpretar referencias — `run_provider_step`/
`validate_generated_content` reciben únicamente `transcript_text` como
`input_text`/`reference_text`, nunca el contexto previo. No hay ruta de
código por la que ese texto pueda alcanzar el grounding: la firma de
`run_provider_step` no lo admite.
"""

from __future__ import annotations

from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.patient_context import PatientContextRequirement, PreviousAnamnesisRef
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.session_notes_generator import SessionNotesGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 55


def _previous_anamnesis_context_text(ref: PreviousAnamnesisRef | None) -> str | None:
    """Conversión mecánica mínima de `PreviousAnamnesisRef` a texto plano
    para el `SessionNotesGenerator` — NO es el prompt real (eso llega con
    la plantilla `session_notes_es_v1`, fuera de este hito). Solo extrae
    los valores ya informados/negados del `content` ya persistido, sin
    ninguna síntesis adicional; existe porque `integrations/domain/` no
    puede importar `PreviousAnamnesisRef` (evita invertir la dependencia
    `ai_pipeline` → `integrations`, ver docstring de
    `session_notes_generator.py`)."""
    if ref is None:
        return None
    informative_values = [
        field_value["value"]
        for field_value in ref.content.values()
        if isinstance(field_value, dict) and field_value.get("value")
    ]
    return "; ".join(informative_values) if informative_values else None


class SessionNotesStep(PipelineStep):
    artifact_type = AIArtifactType.SESSION_NOTES

    def __init__(
        self,
        generator: SessionNotesGenerator,
        token_counter: TokenCounter,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "mock",
        model_name: str | None = "mock-v1",
    ) -> None:
        self._generator = generator
        self._token_counter = token_counter
        self._cost_estimator = cost_estimator
        self._provider_name = provider_name
        self._model_name = model_name

    def depends_on(self) -> frozenset[AIArtifactType]:
        return frozenset({AIArtifactType.TRANSCRIPT})

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        return frozenset({PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS})

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        if context.patient_context is None:
            return False
        return context.patient_context.previous_approved_anamnesis is not None

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]
        previous_ref = (
            context.patient_context.previous_approved_anamnesis
            if context.patient_context is not None
            else None
        )
        previous_anamnesis_context = _previous_anamnesis_context_text(previous_ref)

        async def produce() -> ProduceResult:
            draft = await self._generator.generate(
                transcript_text, previous_anamnesis_context, context=context.session_context
            )
            content: dict[str, Any] = {
                block_name: {"text": block.text, "source_excerpt": block.source_excerpt}
                for block_name, block in draft.blocks.items()
            }
            return content, _CONFIDENCE, None, None, None

        return await run_provider_step(
            artifact_type=self.artifact_type,
            provider_name=self._provider_name,
            model_name=self._model_name,
            token_counter=self._token_counter,
            cost_estimator=self._cost_estimator,
            input_text=transcript_text,
            produce=produce,
            context=context,
        )
