"""Paso 1 del pipeline: transcripción. Sin dependencias."""

from __future__ import annotations

from typing import Any

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext, PipelineStepOutcome
from app.ai_pipeline.domain.steps.base import run_provider_step
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.token_counter import TokenCounter
from app.integrations.domain.transcription_provider import TranscriptionInput, TranscriptionProvider

_DEFAULT_CONFIDENCE = 70


class TranscriptionStep:
    artifact_type = AIArtifactType.TRANSCRIPT

    def __init__(
        self,
        provider: TranscriptionProvider,
        token_counter: TokenCounter,
        cost_estimator: CostEstimator,
        *,
        provider_name: str = "mock",
        model_name: str | None = "mock-v1",
    ) -> None:
        self._provider = provider
        self._token_counter = token_counter
        self._cost_estimator = cost_estimator
        self._provider_name = provider_name
        self._model_name = model_name

    def depends_on(self) -> frozenset[AIArtifactType]:
        return frozenset()

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome:
        async def produce() -> tuple[dict[str, Any], int]:
            result = await self._provider.transcribe(
                TranscriptionInput(
                    clinical_session_id=context.clinical_session_id, audio=context.audio_input
                )
            )
            # `duration_ms`/`segments` (Fase 5) solo se añaden si el
            # proveedor los devuelve (nunca el Mock): el `content` del Mock
            # Pipeline sigue siendo exactamente `{"text", "language"}`, sin
            # cambios — ver docs/ai-pipeline-architecture.md §7.1 y
            # docs/transcription-benchmark.md.
            content: dict[str, Any] = {"text": result.text, "language": result.language}
            if result.duration_ms is not None:
                content["duration_ms"] = result.duration_ms
            if result.segments:
                content["segments"] = [
                    {
                        "speaker": segment.speaker,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "text": segment.text,
                    }
                    for segment in result.segments
                ]
            confidence = result.confidence if result.confidence is not None else _DEFAULT_CONFIDENCE
            return content, confidence

        return await run_provider_step(
            artifact_type=self.artifact_type,
            provider_name=self._provider_name,
            model_name=self._model_name,
            token_counter=self._token_counter,
            cost_estimator=self._cost_estimator,
            # Sin texto de entrada propiamente dicho: la entrada es una
            # referencia de audio/fixture, no texto (ver TranscriptionInput).
            input_text="",
            produce=produce,
        )
