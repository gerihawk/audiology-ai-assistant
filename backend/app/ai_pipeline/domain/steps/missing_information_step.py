"""Paso 4 del pipeline: información ausente. Depende de resumen y señales de alerta."""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import asdict
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.missing_information_generator import MissingInformationGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 60


class MissingInformationStep:
    artifact_type = AIArtifactType.MISSING_INFORMATION

    def __init__(
        self,
        generator: MissingInformationGenerator,
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
        return frozenset({AIArtifactType.SUMMARY, AIArtifactType.CLINICAL_FLAGS})

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        summary_text: str = context.outputs[AIArtifactType.SUMMARY]["text"]
        flags_content: dict[str, Any] = context.outputs[AIArtifactType.CLINICAL_FLAGS]
        clinical_flags = [ClinicalFlagDraft(**flag) for flag in flags_content["flags"]]

        async def produce() -> ProduceResult:
            result = await self._generator.generate(
                summary_text, clinical_flags, context=context.session_context
            )
            content = {"items": [asdict(item) for item in result.items]}
            return (
                content,
                _CONFIDENCE,
                result.input_tokens,
                result.output_tokens,
                result.reasoning_tokens,
            )

        outcome = await run_provider_step(
            artifact_type=self.artifact_type,
            provider_name=self._provider_name,
            model_name=self._model_name,
            token_counter=self._token_counter,
            cost_estimator=self._cost_estimator,
            input_text=summary_text,
            produce=produce,
            context=context,
        )
        return dataclasses.replace(
            outcome,
            prompt_template_id=self._prompt_template_id,
            prompt_template_version=self._prompt_template_version,
        )
