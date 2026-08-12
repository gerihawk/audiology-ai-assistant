"""`GenerationBenchmarkRunner` — encargo de la Fase 6.2 §7.

    carga caso -> selecciona candidato -> PromptTemplate/version activa ->
    PromptRenderer -> invoca modelo (OpenRouter) -> parse -> schema
    validation -> safety -> grounding cuando aplique -> métricas -> gates

Ejecución **secuencial** (encargo §17, sin benchmarking concurrente
todavía). Reutiliza directamente `validate_generated_content` (schema +
evasiva + grounding + safety, en ese orden — RFC §5.1) y `retry_policy`
(mismos motivos tipados/límites que producción) — nunca los reimplementa.

**Nunca crea `AIArtifact`** ni toca `ai_artifacts`/`ai_artifact_versions`/
`ai_generation_runs` — un `GenerationBenchmarkOutcome` es un concepto
propio del benchmark, no un artefacto clínico (encargo §7, "NO persistir
resultados del benchmark como AIArtifact clínico")."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate, RenderContext
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.prompt_renderer import PromptRenderer
from app.ai_pipeline.domain.prompt_template_repository import (
    PromptTemplateNotFoundError,
    PromptTemplateRepository,
    require_active_template,
)
from app.ai_pipeline.domain.retry_policy import backoff_seconds, max_retries_for
from app.ai_pipeline.domain.validation_pipeline import ValidationOutcome, validate_generated_content
from app.core.config import Settings
from benchmark.generation.dataset import GenerationDatasetCase
from benchmark.generation.gates import Finding, GateResult, classify_findings, evaluate_gates
from benchmark.generation.metrics import (
    EvidenceCoverageReport,
    FactPreservationReport,
    HallucinationReport,
    MissingInformationCompletenessReport,
    NumericReport,
    evaluate_evidence_coverage,
    evaluate_forbidden_facts,
    evaluate_missing_information_completeness,
    evaluate_numeric,
    evaluate_required_facts,
    flatten_content_text,
    flatten_missing_information_topics,
)
from benchmark.generation.openrouter_client import (
    BenchmarkLLMClient,
    LlmCompletionRequest,
    LlmCompletionResponse,
    OpenRouterProviderError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)
from benchmark.metrics.laterality import LateralityReport, evaluate_laterality
from benchmark.metrics.negation import NegationReport, evaluate_negations
from benchmark.metrics.terminology import TerminologyReport, evaluate_terminology


class GenerationReferenceRequiredError(ValueError):
    """El caso no tiene `reference.json` con contenido — nunca se invoca
    un modelo real sin referencia humana (encargo Fase 6.2 §23/§25)."""


@dataclass(slots=True, frozen=True)
class MetricsBundle:
    required_facts: FactPreservationReport | None
    hallucination: HallucinationReport | None
    negations: NegationReport | None
    laterality: LateralityReport | None
    numeric: NumericReport | None
    terminology: TerminologyReport | None
    missing_information_completeness: MissingInformationCompletenessReport | None
    evidence_coverage: EvidenceCoverageReport | None
    #: MISSING_INFORMATION únicamente — mismo `HallucinationReport` que
    #: `hallucination`, pero para un concepto distinto (RFC diagnóstico
    #: post-mortem 2026-08-12): un `topic` que coincide con un patrón que
    #: metadata declara ya suficientemente cubierto no es una alucinación
    #: clínica, así que nunca comparte gate/severidad con `hallucination`
    #: — ver `classify_findings` y docs/generation-benchmark.md.
    missing_topic_false_positives: HallucinationReport | None


@dataclass(slots=True, frozen=True)
class GenerationBenchmarkOutcome:
    case_id: str
    artifact_type: AIArtifactType
    model: str
    ran_at: str
    latency_ms: int
    attempts: int
    prompt_template_id: uuid.UUID
    prompt_template_version: int
    llm_response: LlmCompletionResponse | None
    validation: ValidationOutcome
    metrics: MetricsBundle
    gates: GateResult
    findings: list[Finding]
    #: Error de transporte (timeout/rate limit/provider) del último
    #: intento agotado — `None` si el fallo (si lo hay) es de validación
    #: de contenido, no de red.
    transport_error: str | None

    @property
    def succeeded(self) -> bool:
        return self.validation.ok


def _map_transport_error(exc: Exception) -> AIGenerationFailureReason:
    if isinstance(exc, OpenRouterTimeoutError):
        return AIGenerationFailureReason.PROVIDER_TIMEOUT
    if isinstance(exc, OpenRouterRateLimitError):
        return AIGenerationFailureReason.PROVIDER_RATE_LIMITED
    if isinstance(exc, OpenRouterProviderError) and exc.status_code >= 500:
        return AIGenerationFailureReason.PROVIDER_UNAVAILABLE
    # 4xx distinto de rate limit (p. ej. modelo inexistente, payload
    # rechazado): no es transitorio, reintentarlo no lo arregla.
    return AIGenerationFailureReason.UNEXPECTED_INTERNAL_ERROR


def _correction_note_for(reason: AIGenerationFailureReason) -> str:
    return (
        f"\n\n[Corrección: la respuesta anterior falló la validación ({reason.value}). "
        "Ajusta el contenido para cumplir estrictamente las reglas y el formato JSON "
        "exacto, sin añadir nuevos datos clínicos.]"
    )


class GenerationBenchmarkRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        prompt_template_repository: PromptTemplateRepository,
        db_session: AsyncSession,
        llm_client: BenchmarkLLMClient | None = None,
    ) -> None:
        self._settings = settings
        self._prompt_repository = prompt_template_repository
        self._db_session = db_session
        self._injected_client = llm_client

    async def _resolve_template(self, case: GenerationDatasetCase) -> PromptTemplate:
        pinned = case.input.prompt_template
        if pinned is not None:
            template = await self._prompt_repository.get_active_by_name(
                self._db_session, pinned.name
            )
            if template is None:
                raise PromptTemplateNotFoundError(case.input.artifact_type, case.input.language)
            return template
        return await require_active_template(
            self._db_session, self._prompt_repository, case.input.artifact_type, case.input.language
        )

    def _build_variables(
        self, case: GenerationDatasetCase, template: PromptTemplate
    ) -> dict[str, str]:
        # `transcript` solo se inyecta si la plantilla la declara — algunas
        # (p. ej. missing_information_es_v1) no la usan directamente y
        # `PromptRenderer` rechaza cualquier variable no declarada en
        # `variables_schema` (ver prompt_renderer.py).
        variables = dict(case.input.context)
        declared = set(template.variables_schema.get("required", [])) | set(
            template.variables_schema.get("optional", [])
        )
        if "transcript" in declared:
            variables.setdefault("transcript", case.input.transcript)
        return variables

    def _should_retry(self, reason: AIGenerationFailureReason | None, attempts: int) -> bool:
        if reason is None:
            return False
        max_retries = max_retries_for(
            reason,
            max_general=self._settings.ai_pipeline_max_general_retries,
            max_regenerative=self._settings.ai_pipeline_max_regenerative_retries,
        )
        return attempts <= max_retries

    async def _sleep_backoff(self, attempts: int) -> None:
        delay = backoff_seconds(
            attempts - 1, base_seconds=self._settings.ai_pipeline_retry_backoff_base_seconds
        )
        if delay > 0:
            await asyncio.sleep(delay)

    async def run_one(
        self, case: GenerationDatasetCase, *, model: str
    ) -> GenerationBenchmarkOutcome:
        if case.reference is None:
            raise GenerationReferenceRequiredError(
                f"'{case.id}' no tiene reference.json con contenido — no se invoca un "
                "modelo real sin referencia humana (encargo Fase 6.2 §23/§25)."
            )

        template = await self._resolve_template(case)
        client = self._injected_client or BenchmarkLLMClient(
            api_key=self._settings.openrouter_api_key,
            base_url=self._settings.openrouter_base_url,
            timeout_seconds=self._settings.openrouter_timeout_seconds,
        )

        rendered = PromptRenderer().render(
            template, RenderContext(variables=self._build_variables(case, template))
        )

        ran_at = datetime.now(UTC).isoformat()
        started_total = time.perf_counter()
        attempts = 0
        correction_note = ""
        llm_response: LlmCompletionResponse | None = None
        validation: ValidationOutcome | None = None
        transport_error: str | None = None

        while True:
            attempts += 1
            try:
                llm_response = await client.complete(
                    LlmCompletionRequest(
                        model=model,
                        system_prompt=rendered.system_prompt,
                        user_prompt=rendered.user_prompt + correction_note,
                        temperature=0.0,
                        max_output_tokens=self._settings.llm_max_output_tokens_estimate,
                    )
                )
            except (
                OpenRouterTimeoutError,
                OpenRouterRateLimitError,
                OpenRouterProviderError,
            ) as exc:
                reason = _map_transport_error(exc)
                transport_error = str(exc)
                llm_response = None
                if self._should_retry(reason, attempts):
                    await self._sleep_backoff(attempts)
                    continue
                validation = ValidationOutcome(
                    ok=False, content=None, source_map=None, failure_reason=reason
                )
                break

            transport_error = None
            try:
                content: Any = json.loads(llm_response.raw_text)
            except json.JSONDecodeError:
                reason = AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
                if self._should_retry(reason, attempts):
                    correction_note = _correction_note_for(reason)
                    await self._sleep_backoff(attempts)
                    continue
                validation = ValidationOutcome(
                    ok=False, content=None, source_map=None, failure_reason=reason
                )
                break

            validation = validate_generated_content(
                case.input.artifact_type, content, case.input.transcript
            )
            if validation.ok or not self._should_retry(validation.failure_reason, attempts):
                break
            correction_note = _correction_note_for(validation.failure_reason)
            await self._sleep_backoff(attempts)

        latency_ms = int((time.perf_counter() - started_total) * 1000)
        assert validation is not None  # el bucle siempre termina con una validación asignada
        return self._build_outcome(
            case=case,
            model=model,
            ran_at=ran_at,
            latency_ms=latency_ms,
            attempts=attempts,
            template=template,
            llm_response=llm_response,
            validation=validation,
            transport_error=transport_error,
        )

    def _build_outcome(
        self,
        *,
        case: GenerationDatasetCase,
        model: str,
        ran_at: str,
        latency_ms: int,
        attempts: int,
        template: PromptTemplate,
        llm_response: LlmCompletionResponse | None,
        validation: ValidationOutcome,
        transport_error: str | None,
    ) -> GenerationBenchmarkOutcome:
        required_facts = hallucination = negations = laterality = numeric = None
        terminology = missing_information_completeness = None
        missing_topic_false_positives = None
        evidence_coverage = evaluate_evidence_coverage(validation.content, validation.source_map)

        if validation.ok and case.metadata is not None:
            generated_text = flatten_content_text(validation.content)
            if case.metadata.required_facts:
                required_facts = evaluate_required_facts(
                    generated_text, case.metadata.required_facts
                )
            if case.metadata.forbidden_facts:
                if case.input.artifact_type is AIArtifactType.MISSING_INFORMATION:
                    # MISSING_INFORMATION: un `topic` que coincide con un
                    # forbidden_fact no es una alucinación clínica — el
                    # modelo no afirma ningún hecho fabricado, solo
                    # propone revisitar algo que metadata ya declara
                    # suficientemente cubierto (encargo Fase 6.2,
                    # diagnóstico post-mortem 2026-08-12, caso real:
                    # sonnet-5 proponiendo "exposición laboral" ya
                    # conocida). Nunca alimenta `hallucination`/GATE 2 —
                    # ver `classify_findings` (MAJOR,
                    # `missing_topic_false_positive`) y
                    # docs/generation-benchmark.md. Sigue mirando solo
                    # `items[].topic`, no `suggested_question` (mismo
                    # razonamiento que motivó ese scoping).
                    missing_topic_false_positives = evaluate_forbidden_facts(
                        flatten_missing_information_topics(validation.content),
                        case.metadata.forbidden_facts,
                    )
                else:
                    hallucination = evaluate_forbidden_facts(
                        generated_text, case.metadata.forbidden_facts
                    )
            if case.metadata.negation_cases:
                negations = evaluate_negations(generated_text, case.metadata.negation_cases)
            if case.metadata.laterality_cases:
                laterality = evaluate_laterality(generated_text, case.metadata.laterality_cases)
            if case.metadata.numeric_cases:
                numeric = evaluate_numeric(generated_text, case.metadata.numeric_cases)
            if case.metadata.critical_terms:
                terminology = evaluate_terminology(
                    case.input.transcript, generated_text, case.metadata.critical_terms
                )
            if (
                case.input.artifact_type is AIArtifactType.MISSING_INFORMATION
                and case.metadata.expected_missing_topics
            ):
                missing_information_completeness = evaluate_missing_information_completeness(
                    validation.content, case.metadata.expected_missing_topics
                )

        gates = evaluate_gates(
            validation=validation,
            hallucination=hallucination,
            negations=negations,
            laterality=laterality,
        )
        findings = classify_findings(
            validation=validation,
            hallucination=hallucination,
            required_facts=required_facts,
            negations=negations,
            laterality=laterality,
            numeric=numeric,
            terminology=terminology,
            missing_information_completeness=missing_information_completeness,
            missing_topic_false_positives=missing_topic_false_positives,
        )

        return GenerationBenchmarkOutcome(
            case_id=case.id,
            artifact_type=case.input.artifact_type,
            model=model,
            ran_at=ran_at,
            latency_ms=latency_ms,
            attempts=attempts,
            prompt_template_id=template.id,
            prompt_template_version=template.version,
            llm_response=llm_response,
            validation=validation,
            metrics=MetricsBundle(
                required_facts=required_facts,
                hallucination=hallucination,
                negations=negations,
                laterality=laterality,
                numeric=numeric,
                terminology=terminology,
                missing_information_completeness=missing_information_completeness,
                evidence_coverage=evidence_coverage,
                missing_topic_false_positives=missing_topic_false_positives,
            ),
            gates=gates,
            findings=findings,
            transport_error=transport_error,
        )
