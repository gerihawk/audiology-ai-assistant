"""Paso 5 (último) del pipeline: anamnesis estructurada.

Depende formalmente de `missing_information` (ver
docs/ai-pipeline-architecture.md §1.4), pero también consume el texto de
la transcripción, ya disponible en `context.outputs` — sin declararlo
como dependencia propia porque un fallo en `transcript` ya provoca en
cascada que `summary`/`clinical_flags` se salten (por su propio
`depends_on()`), y por tanto que `missing_information` se salte, y por
tanto que este paso también se salte: nunca se ejecuta `run()` sin que
`transcript` haya completado con éxito.
"""

from __future__ import annotations

from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.anamnesis_generator import AnamnesisGenerator
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.missing_information_generator import MissingInfoItem
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 55


class AnamnesisStep:
    artifact_type = AIArtifactType.ANAMNESIS

    def __init__(
        self,
        generator: AnamnesisGenerator,
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
        return frozenset({AIArtifactType.MISSING_INFORMATION})

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]
        missing_info_content: dict[str, Any] = context.outputs[AIArtifactType.MISSING_INFORMATION]
        missing_information = [MissingInfoItem(**item) for item in missing_info_content["items"]]

        async def produce() -> ProduceResult:
            draft = await self._generator.generate(
                transcript_text, missing_information, context=context.session_context
            )
            content = {
                field_name: {"value": field_value.value, "status": field_value.status.value}
                for field_name, field_value in draft.fields.items()
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
