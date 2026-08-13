"""Paso 2 del pipeline: resumen. Depende de la transcripción."""

from __future__ import annotations

import dataclasses
import uuid

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.summary_generator import SummaryGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 75


class SummaryStep(PipelineStep):
    artifact_type = AIArtifactType.SUMMARY

    def __init__(
        self,
        generator: SummaryGenerator,
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
        # Fase 6.3.7: `None` en Mock (sin PromptTemplate de por medio) —
        # ver docstring de PipelineStepOutcome.prompt_template_id.
        self._prompt_template_id = prompt_template_id
        self._prompt_template_version = prompt_template_version

    def depends_on(self) -> frozenset[AIArtifactType]:
        return frozenset({AIArtifactType.TRANSCRIPT})

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]

        async def produce() -> ProduceResult:
            draft = await self._generator.generate(transcript_text, context=context.session_context)
            return (
                {"text": draft.text},
                _CONFIDENCE,
                draft.input_tokens,
                draft.output_tokens,
                draft.reasoning_tokens,
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
