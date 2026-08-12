"""Paso del pipeline: resumen para el paciente (Fase 6.3, RFC §4.3).

Depende formalmente solo de `TRANSCRIPT` — `SUMMARY` es una dependencia
blanda: se usa cuando esa misma ejecución ya lo produjo, pero un fallo o
salto de `SUMMARY` nunca bloquea este paso (RFC: "cuando esté disponible en
la ejecución"). Debe ejecutarse después de `SUMMARY` en `PIPELINE_STEP_ORDER`
para que `context.outputs` ya lo tenga poblado si tuvo éxito — el orden no
lo impone `depends_on()`, lo impone la lista que construye
`AIPipelineService._build_steps()`.
"""

from __future__ import annotations

import dataclasses
import uuid

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.patient_summary_generator import PatientSummaryGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 70


class PatientSummaryStep:
    artifact_type = AIArtifactType.PATIENT_SUMMARY

    def __init__(
        self,
        generator: PatientSummaryGenerator,
        token_counter: TokenCounter,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "mock",
        model_name: str | None = "mock-v1",
        prompt_template_id: uuid.UUID | None = None,
        prompt_template_version: int | None = None,
    ) -> None:
        self._generator = generator
        self._token_counter = token_counter
        self._cost_estimator = cost_estimator
        self._provider_name = provider_name
        self._model_name = model_name
        self._prompt_template_id = prompt_template_id
        self._prompt_template_version = prompt_template_version

    def depends_on(self) -> frozenset[AIArtifactType]:
        return frozenset({AIArtifactType.TRANSCRIPT})

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]
        # Dependencia blanda: `SUMMARY` puede no existir en esta ejecución
        # (fallo, salto, o simplemente no se llegó a ejecutar) — nunca es
        # motivo para que este paso falle, solo se pierde el enriquecimiento.
        summary_output = context.outputs.get(AIArtifactType.SUMMARY)
        summary_text: str = summary_output["text"] if summary_output else ""

        async def produce() -> ProduceResult:
            draft = await self._generator.generate(
                transcript_text, summary_text, context=context.session_context
            )
            return (
                {"text": draft.text},
                _CONFIDENCE,
                draft.input_tokens,
                draft.output_tokens,
            )

        outcome = await run_provider_step(
            artifact_type=self.artifact_type,
            provider_name=self._provider_name,
            model_name=self._model_name,
            token_counter=self._token_counter,
            cost_estimator=self._cost_estimator,
            input_text=transcript_text,
            produce=produce,
            context=context,
        )
        return dataclasses.replace(
            outcome,
            prompt_template_id=self._prompt_template_id,
            prompt_template_version=self._prompt_template_version,
        )
