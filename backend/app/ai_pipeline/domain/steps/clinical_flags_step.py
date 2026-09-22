"""Paso 3 del pipeline: señales de alerta. Depende de la transcripción.

Independiente de `summary` (ambos solo dependen de `transcript`) — ver
docs/ai-pipeline-architecture.md §1.4.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import asdict

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.clinical_flags_generator import ClinicalFlagsGenerator
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 65


class ClinicalFlagsStep(PipelineStep):
    artifact_type = AIArtifactType.CLINICAL_FLAGS

    def __init__(
        self,
        generator: ClinicalFlagsGenerator,
        token_counter: TokenCounter,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "mock",
        model_name: str | None = None,
        prompt_template_id: uuid.UUID | None = None,
        prompt_template_version: int | None = None,
    ) -> None:
        # `model_name`/`prompt_template_id`/`prompt_template_version` en
        # `None` por defecto: la implementación de referencia es un
        # checklist basado en reglas, no un modelo de lenguaje (ver
        # docs/ai-pipeline-architecture.md §6.1). Ampliación 2026-09-21
        # (docs/clinical-safety.md §7): cuando `provider_name != "mock"`
        # (`RealClinicalFlagsGenerator`, gated por
        # `Settings.llm_provider_clinical_flags`), `_build_clinical_flags_step`
        # sí los rellena — mismo patrón que `MissingInformationStep`.
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

        async def produce() -> ProduceResult:
            flags = await self._generator.generate(transcript_text, context=context.session_context)
            content = {"flags": [asdict(flag) for flag in flags]}
            # Basado en reglas (Mock) o LLM real: en ambos casos el propio
            # generador decide qué usage reportar — el mock nunca gasta
            # tokens (None, None, None); `RealClinicalFlagsGenerator`
            # todavía no reporta usage real (Fase de esta ampliación no lo
            # exige, a diferencia de `RealMissingInformationGenerator`) —
            # `run_provider_step` cae al `TokenCounter` heurístico como ya
            # hace para cualquier proveedor sin usage reportado.
            return content, _CONFIDENCE, None, None, None

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
