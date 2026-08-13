"""Paso 5 (último) del pipeline: anamnesis estructurada.

Depende formalmente de `missing_information` (ver
docs/ai-pipeline-architecture.md §1.4), pero también consume el texto de
la transcripción, ya disponible en `context.outputs` — sin declararlo
como dependencia propia porque un fallo en `transcript` ya provoca en
cascada que `summary`/`clinical_flags` se salten (por su propio
`depends_on()`), y por tanto que `missing_information` se salte, y por
tanto que este paso también se salte: nunca se ejecuta `run()` sin que
`transcript` haya completado con éxito.

`applies_to()` (Fase 6.4.2, RFC técnico §5): `True` solo si el paciente
no tiene ya una `ANAMNESIS` aprobada de OTRA sesión en esta clínica —
`session_type` nunca determina esta decisión (RFC §2/§4). El propio
`source_excerpt` de cada campo se valida contra el transcript ACTUAL
únicamente (RFC técnico §7): este step nunca pasa el contexto
longitudinal a `run_provider_step`/`validate_generated_content`, solo al
`AnamnesisGenerator` para enriquecer el prompt — dos canales separados
por firma de tipos, no por convención.
"""

from __future__ import annotations

from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.patient_context import PatientContextRequirement
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineStep,
    PipelineStepOutcome,
)
from app.ai_pipeline.domain.steps.base import ProduceResult, run_provider_step
from app.integrations.domain.anamnesis_generator import AnamnesisGenerator
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.missing_information_generator import MissingInfoItem
from app.integrations.domain.token_counter import TokenCounter

_CONFIDENCE = 55


class AnamnesisStep(PipelineStep):
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

    def patient_context_requirements(self) -> frozenset[PatientContextRequirement]:
        return frozenset({PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS})

    def applies_to(self, context: PipelineExecutionContext) -> bool:
        """`True` si no existe ya una anamnesis aprobada del paciente
        procedente de otra sesión (RFC técnico §5). Puro: solo lee
        `context.patient_context`, ya resuelto por `AIPipelineService`
        antes de invocar al orquestador — nunca consulta un repositorio.

        `context.patient_context is None` (contexto nunca cargado, p. ej.
        un `PipelineExecutionContext` construido a mano en un test sin
        pasar por el servicio) se trata como "sin anamnesis previa
        conocida" y por tanto aplica — mismo comportamiento por defecto
        que tenía este step antes de 6.4.2, nunca se salta por una
        ausencia de dato que no es responsabilidad suya resolver."""
        if context.patient_context is None:
            return True
        return context.patient_context.previous_approved_anamnesis is None

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        transcript_text: str = context.outputs[AIArtifactType.TRANSCRIPT]["text"]
        missing_info_content: dict[str, Any] = context.outputs[AIArtifactType.MISSING_INFORMATION]
        missing_information = [MissingInfoItem(**item) for item in missing_info_content["items"]]

        async def produce() -> ProduceResult:
            draft = await self._generator.generate(
                transcript_text, missing_information, context=context.session_context
            )
            content = {
                field_name: {
                    "value": field_value.value,
                    "status": field_value.status.value,
                    "source_excerpt": field_value.source_excerpt,
                }
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
