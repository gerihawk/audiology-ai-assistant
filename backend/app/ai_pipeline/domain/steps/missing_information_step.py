"""Paso 4 del pipeline: información ausente. Depende de resumen y señales
de alerta.

`applies_to()`/target-awareness (Fase 6.4.4, RFC técnico de 6.4 §2-§4):
el esquema objetivo contra el que se evalúan los gaps (`ANAMNESIS_FIELDS`
o `SESSION_NOTES_BLOCKS`) lo decide `resolve_missing_information_target`
a partir de `context.patient_context` — la MISMA fuente de verdad que
`AnamnesisStep.applies_to()`/`SessionNotesStep.applies_to()` (§3, "no
dupliques reglas inconsistentes"). Este step corre ANTES de `ANAMNESIS`/
`SESSION_NOTES` en `PIPELINE_STEP_ORDER`, así que no puede derivar el
target de `context.outputs[ANAMNESIS]` — debe leer `context.patient_context`
directamente, igual que sus dos "hermanos" posteriores. El LLM/Mock nunca
elige el target: lo recibe ya resuelto."""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import asdict
from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.patient_context import (
    PatientContextRequirement,
    resolve_missing_information_target,
)
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.missing_information_generator import MissingInformationGenerator
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 60


class MissingInformationStep(PipelineStep):
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

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        return frozenset({PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS})

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        """`True` si existe un target válido — bajo el modelo actual,
        siempre uno de los dos (`resolve_missing_information_target`
        nunca inventa un target por defecto). `target is None` solo es
        alcanzable si `patient_context` nunca se cargó; se maneja
        defensivamente aquí en vez de asumir un target arbitrario."""
        return resolve_missing_information_target(context.patient_context) is not None

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        summary_text: str = context.outputs[AIArtifactType.SUMMARY]["text"]
        flags_content: dict[str, Any] = context.outputs[AIArtifactType.CLINICAL_FLAGS]
        clinical_flags = [ClinicalFlagDraft(**flag) for flag in flags_content["flags"]]
        target = resolve_missing_information_target(context.patient_context)
        assert target is not None  # invariante: applies_to() ya lo garantizó antes de run()

        async def produce() -> ProduceResult:
            result = await self._generator.generate(
                summary_text, clinical_flags, target=target, context=context.session_context
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
