"""Paso 2 del pipeline: resumen. Depende de la transcripción."""

from __future__ import annotations

from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import run_provider_step
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.summary_generator import SummaryGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 75


class SummaryStep:
    artifact_type = AIArtifactType.SUMMARY

    def __init__(
        self,
        generator: SummaryGenerator,
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

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]

        async def produce() -> tuple[dict[str, Any], int]:
            draft = await self._generator.generate(transcript_text, context=context.session_context)
            return {"text": draft.text}, _CONFIDENCE

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
