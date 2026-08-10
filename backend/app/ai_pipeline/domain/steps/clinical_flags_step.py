"""Paso 3 del pipeline: señales de alerta. Depende de la transcripción.

Independiente de `summary` (ambos solo dependen de `transcript`) — ver
docs/ai-pipeline-architecture.md §1.4.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import run_provider_step
from app.integrations.domain.clinical_flags_generator import ClinicalFlagsGenerator
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 65


class ClinicalFlagsStep:
    artifact_type = AIArtifactType.CLINICAL_FLAGS

    def __init__(
        self,
        generator: ClinicalFlagsGenerator,
        token_counter: TokenCounter,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "mock",
        model_name: str | None = None,
    ) -> None:
        # `model_name=None` por defecto: la implementación de referencia es
        # un checklist basado en reglas, no un modelo de lenguaje (ver
        # docs/ai-pipeline-architecture.md §6.1).
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
            flags = await self._generator.generate(transcript_text, context=context.session_context)
            content = {"flags": [asdict(flag) for flag in flags]}
            return content, _CONFIDENCE

        return await run_provider_step(
            artifact_type=self.artifact_type,
            provider_name=self._provider_name,
            model_name=self._model_name,
            token_counter=self._token_counter,
            cost_estimator=self._cost_estimator,
            input_text=transcript_text,
            produce=produce,
        )
