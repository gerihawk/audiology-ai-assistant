"""AIPipelineService: autoriza → ejecuta el pipeline → persiste → audita → commit.

Mismo patrón transaccional que `ClinicalSessionService`/`PatientService`: la
escritura de todas las entidades tocadas (artefactos, versiones,
ejecuciones, auditoría) se confirma con un único commit; si algo falla de
forma inesperada (no un simple fallo de proveedor, que se captura y
registra como `AIGenerationRunStatus.FAILED` sin abortar el resto), todo
se revierte.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.anamnesis_update import changed_field_names, reason_for_previous_status
from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.cost_budget import SessionCostBudget
from app.ai_pipeline.domain.entities import (
    PIPELINE_STEP_ORDER,
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
    AIGenerationRun,
    AIGenerationRunStatus,
    AIPipelineRun,
    AIPipelineRunStatus,
    PromptTemplate,
)
from app.ai_pipeline.domain.generation_run_repository import AIGenerationRunRepository
from app.ai_pipeline.domain.patient_context import (
    LoadedPatientContext,
    PatientContextRequirement,
    PreviousAnamnesisRef,
)
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    PipelineOrchestrator,
    PipelineStep,
    PipelineStepOutcome,
    SequentialPipelineOrchestrator,
    SkipReasonCode,
)
from app.ai_pipeline.domain.pipeline_run_repository import AIPipelineRunRepository
from app.ai_pipeline.domain.prompt_template_repository import (
    PromptTemplateNotFoundError,
    PromptTemplateRepository,
    require_active_template,
)
from app.ai_pipeline.domain.retry_policy import RetryConfig
from app.ai_pipeline.domain.schemas import validate_content_schema
from app.ai_pipeline.domain.steps.anamnesis_step import AnamnesisStep
from app.ai_pipeline.domain.steps.anamnesis_update_step import AnamnesisUpdateStep
from app.ai_pipeline.domain.steps.clinical_flags_step import ClinicalFlagsStep
from app.ai_pipeline.domain.steps.missing_information_step import MissingInformationStep
from app.ai_pipeline.domain.steps.patient_summary_step import PatientSummaryStep
from app.ai_pipeline.domain.steps.session_notes_step import SessionNotesStep
from app.ai_pipeline.domain.steps.summary_step import SummaryStep
from app.ai_pipeline.domain.steps.transcription_step import TranscriptionStep
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIArtifactRepository,
    SqlAlchemyAIGenerationRunRepository,
    SqlAlchemyAIPipelineRunRepository,
    SqlAlchemyPromptTemplateRepository,
)
from app.audio.domain.audio_storage import AudioStorage, StorageReference
from app.audio.domain.repository import AudioRecordingRepository
from app.audio.infrastructure.local_audio_storage import LocalAudioStorage
from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_sessions.domain.entities import ClinicalSession
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.consents.domain.entities import ConsentType
from app.consents.domain.repository import ConsentRepository
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.core.authorization import (
    AIArtifactAction,
    AIPipelineAction,
    AudioRecordingAction,
    authorize_ai_artifact_action,
    authorize_ai_pipeline_action,
    authorize_audio_recording_action,
)
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError, SchemaValidationError
from app.core.processing_status import ProcessingStatus
from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus, AnamnesisGenerator
from app.integrations.domain.anamnesis_update_generator import AnamnesisUpdateGenerator
from app.integrations.domain.clinical_flags_generator import ClinicalFlagsGenerator
from app.integrations.domain.cost_estimator import CostEstimator
from app.integrations.domain.missing_information_generator import MissingInformationGenerator
from app.integrations.domain.patient_summary_generator import PatientSummaryGenerator
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.session_notes_generator import SessionNotesGenerator
from app.integrations.domain.summary_generator import SummaryGenerator
from app.integrations.domain.token_counter import TokenCounter
from app.integrations.domain.transcription_provider import (
    AudioForTranscription,
    TranscriptionProvider,
)
from app.integrations.factory import build_language_model_provider
from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator
from app.integrations.mocks.mock_anamnesis_update_generator import MockAnamnesisUpdateGenerator
from app.integrations.mocks.mock_clinical_flags_generator import MockClinicalFlagsGenerator
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from app.integrations.mocks.mock_missing_information_generator import (
    MockMissingInformationGenerator,
)
from app.integrations.mocks.mock_patient_summary_generator import MockPatientSummaryGenerator
from app.integrations.mocks.mock_session_notes_generator import MockSessionNotesGenerator
from app.integrations.mocks.mock_summary_generator import MockSummaryGenerator
from app.integrations.mocks.mock_token_counter import MockTokenCounter
from app.integrations.mocks.mock_transcription_provider import MockTranscriptionProvider
from app.integrations.providers.pricing_table_cost_estimator import PricingTableCostEstimator
from app.integrations.providers.real_missing_information_generator import (
    RealMissingInformationGenerator,
)
from app.integrations.providers.real_patient_summary_generator import (
    RealPatientSummaryGenerator,
)
from app.integrations.providers.real_summary_generator import RealSummaryGenerator

#: Único idioma soportado en runtime — no existe todavía selector de
#: idioma (ver docs/architecture.md §8, fuera de alcance de esta fase).
#: Usado para resolver la `PromptTemplate` activa de cada artifact_type
#: con routing real (Fase 6.3.7).
_DEFAULT_LANGUAGE = "es"


@dataclass(slots=True)
class AIArtifactDetail:
    """Combina el sobre `AIArtifact` con su versión y ejecución vigentes —
    todo lo que necesita la capa de API para una sola respuesta, sin que
    el router tenga que hacer sus propias consultas."""

    artifact: AIArtifact
    current_version: AIArtifactVersion | None
    generation_run: AIGenerationRun | None


@dataclass(slots=True)
class PipelineRunOutcome:
    pipeline_run: AIPipelineRun
    artifacts: list[AIArtifactDetail]
    outcomes: list[PipelineStepOutcome]


@dataclass(slots=True)
class AnamnesisUpdateProposalOutcome:
    """Resultado de `propose_anamnesis_update` (Hito 6.5.3). `detail` es
    `None` exactamente cuando `changed_fields` está vacío — el generador no
    propuso ningún cambio real, así que no se persistió ningún
    `AIArtifact`/`AIArtifactVersion` (RFC técnico de 6.5 §9 del encargo de
    6.5.3: "no changes proposed" es un resultado válido, nunca un fallo ni
    una versión artificial)."""

    detail: AIArtifactDetail | None
    changed_fields: list[str]


@dataclass(slots=True)
class AIArtifactVersionDetail:
    """Una fila del historial — combina la versión con su ejecución (si la
    generó IA) y si es la vigente del artefacto."""

    version: AIArtifactVersion
    generation_run: AIGenerationRun | None
    is_current: bool


class AIPipelineService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        artifact_repository: AIArtifactRepository | None = None,
        generation_run_repository: AIGenerationRunRepository | None = None,
        pipeline_run_repository: AIPipelineRunRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
        orchestrator: PipelineOrchestrator | None = None,
        transcription_provider: TranscriptionProvider | None = None,
        summary_generator: SummaryGenerator | None = None,
        patient_summary_generator: PatientSummaryGenerator | None = None,
        clinical_flags_generator: ClinicalFlagsGenerator | None = None,
        missing_information_generator: MissingInformationGenerator | None = None,
        anamnesis_generator: AnamnesisGenerator | None = None,
        anamnesis_update_generator: AnamnesisUpdateGenerator | None = None,
        session_notes_generator: SessionNotesGenerator | None = None,
        token_counter: TokenCounter | None = None,
        cost_estimator: CostEstimator | None = None,
        llm_cost_estimator: CostEstimator | None = None,
        audio_repository: AudioRecordingRepository | None = None,
        audio_storage: AudioStorage | None = None,
        configured_transcription_provider: TranscriptionProvider | None = None,
        consent_repository: ConsentRepository | None = None,
        prompt_template_repository: PromptTemplateRepository | None = None,
    ) -> None:
        self._session = session
        self._artifacts = artifact_repository or SqlAlchemyAIArtifactRepository()
        self._generation_runs = generation_run_repository or SqlAlchemyAIGenerationRunRepository()
        self._pipeline_runs = pipeline_run_repository or SqlAlchemyAIPipelineRunRepository()
        # Activado vía DI desde el hito 6.1; usado desde el hito 6.3.3/6.3.7
        # por `_require_prompt_template()`/`_build_*_step()` para resolver
        # la plantilla activa de cada artifact_type con routing real — los
        # `Mock*Generator` siguen con su prompt hardcodeado, nunca lo tocan.
        self._prompt_templates = prompt_template_repository or SqlAlchemyPromptTemplateRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()
        self._consents = consent_repository or SqlAlchemyConsentRepository()
        self._orchestrator = orchestrator or SequentialPipelineOrchestrator()

        # Todos los providers son Mock en esta fase — ver
        # docs/ai-pipeline-architecture.md §6.4. Inyectables para tests y
        # para el día que se sustituyan por proveedores reales, sin tocar
        # el servicio ni el orquestador. `_transcription_provider` es
        # EXCLUSIVO de `run_pipeline` (Mock Pipeline, comportamiento sin
        # cambios en la Fase 5) — nunca se resuelve por configuración.
        self._transcription_provider = transcription_provider or MockTranscriptionProvider()
        self._summary_generator = summary_generator or MockSummaryGenerator()
        self._patient_summary_generator = patient_summary_generator or MockPatientSummaryGenerator()
        self._clinical_flags_generator = clinical_flags_generator or MockClinicalFlagsGenerator()
        self._missing_information_generator = (
            missing_information_generator or MockMissingInformationGenerator()
        )
        self._anamnesis_generator = anamnesis_generator or MockAnamnesisGenerator()
        # Fase 6.5.3: sin routing real todavía (RFC técnico de 6.5 §16 —
        # pendiente de benchmark propio antes de activar un proveedor real,
        # mismo criterio que ANAMNESIS/SESSION_NOTES). Nunca se construye en
        # `_build_steps()`/`_build_mock_steps()`: `AnamnesisUpdateStep` es
        # una operación explícita, deliberadamente ausente de
        # `PIPELINE_STEP_ORDER` — solo `propose_anamnesis_update()` la usa.
        self._anamnesis_update_generator = (
            anamnesis_update_generator or MockAnamnesisUpdateGenerator()
        )
        self._session_notes_generator = session_notes_generator or MockSessionNotesGenerator()
        self._token_counter = token_counter or MockTokenCounter()
        self._cost_estimator = cost_estimator or MockCostEstimator()
        # Fase 6.3.8: estimador de coste real, EXCLUSIVO de los steps con
        # routing != "mock" (ver `_build_summary_step` y hermanos) — nunca
        # se usa para los steps que siguen en Mock, cuyo `provider_name`/
        # `model_name` ("mock"/"mock-v1") no tienen precio y no deberían
        # tenerlo (`MockCostEstimator` sigue siendo su estimador, coste 0
        # coherente con que todo es ficticio). Mismo patrón de separación
        # ya usado entre `_transcription_provider` (Mock Pipeline) y
        # `_configured_transcription_provider` (real, Fase 5).
        self._llm_cost_estimator = llm_cost_estimator or PricingTableCostEstimator()

        # Fase 5 — solo usados por `transcribe_from_audio`.
        # `_configured_transcription_provider` es el que sí se resuelve por
        # `TRANSCRIPTION_PROVIDER` (ver app/integrations/factory.py):
        # Mock Pipeline y "transcribir desde audio" son deliberadamente dos
        # rutas independientes, cada una con su propio proveedor.
        self._audio_recordings = audio_repository or SqlAlchemyAudioRecordingRepository()
        settings = get_settings()
        self._audio_storage = audio_storage or LocalAudioStorage(settings.audio_storage_local_dir)
        self._configured_transcription_provider = (
            configured_transcription_provider or MockTranscriptionProvider()
        )

    # --- Disparo del pipeline --------------------------------------------
    #
    # Dos entrypoints deliberadamente distintos (corrección de frontera
    # mock/real, ver docs/fase-6-rfc.md): `run_pipeline` respeta el
    # routing real por artifact_type (`Settings.llm_provider_*`) y puede
    # invocar Anthropic/OpenAI/Google si así está configurado —
    # `POST .../run-pipeline`. `run_mock_pipeline` construye sus steps con
    # `_build_mock_steps()`, que NUNCA lee `Settings.llm_provider_*` ni
    # llama a `build_language_model_provider` — estructuralmente incapaz
    # de alcanzar un proveedor real sin importar la configuración —
    # `POST .../run-mock-pipeline`. Comparten toda la lógica de
    # autorización/consentimiento/persistencia/auditoría vía
    # `_authorize_trigger`/`_execute_pipeline_run`; la única diferencia
    # entre ambos es qué lista de `PipelineStep` se ejecuta.

    async def run_pipeline(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID, request_id: str
    ) -> PipelineRunOutcome:
        """Pipeline CONFIGURADO — respeta `Settings.llm_provider_summary`/
        `llm_provider_patient_summary`/`llm_provider_missing_information`.
        Puede gastar dinero real y enviar datos a un tercero si el routing
        de producción está activo. Expuesto por `POST .../run-pipeline`."""
        clinical_session = await self._authorize_trigger(current_user, clinical_session_id)
        steps = await self._build_steps()
        return await self._execute_pipeline_run(current_user, clinical_session, request_id, steps)

    async def run_mock_pipeline(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID, request_id: str
    ) -> PipelineRunOutcome:
        """Pipeline MOCK — cero LLM externo, determinista, nunca gasta
        dinero, sin importar cómo esté configurado `Settings`
        (`_build_mock_steps()` nunca consulta el routing). Único uso
        legítimo: development/tests/demo. Expuesto por
        `POST .../run-mock-pipeline`."""
        clinical_session = await self._authorize_trigger(current_user, clinical_session_id)
        steps = self._build_mock_steps()
        return await self._execute_pipeline_run(current_user, clinical_session, request_id, steps)

    async def _authorize_trigger(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID
    ) -> ClinicalSession:
        clinical_session = await self._get_clinical_session_or_404(
            current_user, clinical_session_id
        )
        authorize_ai_pipeline_action(
            current_user, AIPipelineAction.TRIGGER, professional_id=clinical_session.professional_id
        )
        await self._ensure_ai_processing_consent(current_user, clinical_session.patient_id)
        return clinical_session

    async def _execute_pipeline_run(
        self,
        current_user: CurrentUser,
        clinical_session: ClinicalSession,
        request_id: str,
        steps: list[PipelineStep],
    ) -> PipelineRunOutcome:
        clinical_session_id = clinical_session.id
        existing_active = await self._pipeline_runs.get_active_for_session(
            self._session, current_user.clinic_id, clinical_session_id
        )
        if existing_active is not None:
            raise ConflictError("Ya existe una ejecución del pipeline en curso para esta sesión.")

        now = datetime.now(UTC)
        pipeline_run = AIPipelineRun(
            id=uuid.uuid4(),
            clinical_session_id=clinical_session_id,
            triggered_by=current_user.id,
            status=AIPipelineRunStatus.PROCESSING,
            started_at=now,
            completed_at=None,
            request_id=request_id,
        )

        try:
            persisted_run = await self._pipeline_runs.add(self._session, pipeline_run)

            cost_budget, retry_config, max_output_tokens_estimate = (
                await self._build_execution_guardrails(clinical_session_id)
            )
            patient_context = await self._resolve_patient_context(
                current_user.clinic_id, clinical_session, steps
            )
            context = PipelineExecutionContext(
                clinical_session_id=clinical_session_id,
                session_context=SessionContext(
                    clinical_session_id=clinical_session_id,
                    session_type=clinical_session.session_type.value,
                ),
                patient_context=patient_context,
                cost_budget=cost_budget,
                retry_config=retry_config,
                max_output_tokens_estimate=max_output_tokens_estimate,
            )
            result = await self._orchestrator.run(context, steps)

            artifact_details: list[AIArtifactDetail] = []
            any_completed = False
            any_failed_or_skipped = False

            for outcome in result.outcomes:
                if outcome.status is None:
                    if _is_problematic_outcome(outcome):
                        any_failed_or_skipped = True
                    continue  # saltado: nunca se invocó, no genera auditoría técnica

                if outcome.status == AIGenerationRunStatus.FAILED:
                    any_failed_or_skipped = True
                    await self._generation_runs.add(
                        self._session,
                        AIGenerationRun(
                            id=uuid.uuid4(),
                            ai_pipeline_run_id=persisted_run.id,
                            clinical_session_id=clinical_session_id,
                            artifact_type=outcome.artifact_type,
                            ai_artifact_id=None,
                            resulting_version_number=None,
                            status=outcome.status,
                            provider_name=outcome.provider_name or "mock",
                            model_name=outcome.model_name,
                            prompt_template_id=outcome.prompt_template_id,
                            prompt_template_version=outcome.prompt_template_version,
                            input_token_count=outcome.input_token_count,
                            output_token_count=outcome.output_token_count,
                            estimated_cost_usd=outcome.estimated_cost_usd,
                            latency_ms=outcome.latency_ms,
                            execution_time_ms=outcome.execution_time_ms,
                            rendered_system_prompt=None,
                            rendered_user_prompt=None,
                            raw_response=outcome.provider_metadata,
                            started_at=outcome.started_at or now,
                            completed_at=outcome.completed_at,
                            failure_reason=outcome.failure_reason,
                            request_id=request_id,
                        ),
                    )
                    continue

                any_completed = True
                detail = await self._persist_completed_outcome(
                    current_user, persisted_run.id, clinical_session_id, outcome, request_id
                )
                artifact_details.append(detail)

            final_status = _resolve_pipeline_status(any_completed, any_failed_or_skipped)
            updated_run = await self._pipeline_runs.update_fields(
                self._session,
                persisted_run.id,
                {"status": final_status, "completed_at": datetime.now(UTC)},
            )
            assert updated_run is not None  # ya verificado: acabamos de crearla

            await self._write_audit(
                current_user,
                request_id,
                action="ai_pipeline.triggered",
                entity_type="ai_pipeline_run",
                entity_id=persisted_run.id,
                metadata={
                    "outcomes": {
                        outcome.artifact_type.value: (
                            outcome.status.value if outcome.status is not None else "skipped"
                        )
                        for outcome in result.outcomes
                    }
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return PipelineRunOutcome(
            pipeline_run=updated_run, artifacts=artifact_details, outcomes=result.outcomes
        )

    async def _persist_completed_outcome(
        self,
        current_user: CurrentUser,
        pipeline_run_id: uuid.UUID,
        clinical_session_id: uuid.UUID,
        outcome: PipelineStepOutcome,
        request_id: str,
        *,
        baseline_artifact_id: uuid.UUID | None = None,
        baseline_version_id: uuid.UUID | None = None,
    ) -> AIArtifactDetail:
        """`baseline_artifact_id`/`baseline_version_id` (Hito 6.5.3): solo
        los usa `propose_anamnesis_update()` — `None` para el resto de
        llamadores (comportamiento histórico sin cambios). Se fijan
        ÚNICAMENTE al crear el `AIArtifact` la primera vez
        (`existing_artifact is None`): un rerun sobre un artefacto ya
        existente nunca los toca — son identidad del baseline original de
        la propuesta, no del intento de contenido más reciente (auditoría
        de 6.5, §2 del encargo de 6.5.3)."""
        existing_artifact = await self._artifacts.get_by_session_and_type(
            self._session, current_user.clinic_id, clinical_session_id, outcome.artifact_type
        )
        now = datetime.now(UTC)

        # Orden de inserción impuesto por las FKs circulares del esquema
        # (ver docs/data-model.md §10): el AIArtifact debe existir ya
        # (aunque sea sin versión vigente) antes de poder insertar la
        # AIArtifactVersion y el AIGenerationRun que la referencian; solo
        # entonces se actualiza `current_version_id`.
        if existing_artifact is None:
            artifact_id = uuid.uuid4()
            next_version_number = 1
            await self._artifacts.insert_new(
                self._session,
                AIArtifact(
                    id=artifact_id,
                    clinical_session_id=clinical_session_id,
                    artifact_type=outcome.artifact_type,
                    status=AIArtifactStatus.REVIEW_PENDING,
                    current_version_id=None,
                    confidence=None,
                    schema_version=1,
                    approved_by=None,
                    approved_at=None,
                    rejected_by=None,
                    rejected_at=None,
                    rejection_reason=None,
                    deleted_by=None,
                    deleted_at=None,
                    created_at=now,
                    updated_at=now,
                    baseline_artifact_id=baseline_artifact_id,
                    baseline_version_id=baseline_version_id,
                ),
            )
        else:
            artifact_id = existing_artifact.id
            next_version_number = (
                await self._artifacts.latest_version_number(self._session, artifact_id) + 1
            )

        generation_run = AIGenerationRun(
            id=uuid.uuid4(),
            ai_pipeline_run_id=pipeline_run_id,
            clinical_session_id=clinical_session_id,
            artifact_type=outcome.artifact_type,
            ai_artifact_id=artifact_id,
            resulting_version_number=next_version_number,
            status=AIGenerationRunStatus.COMPLETED,
            provider_name=outcome.provider_name or "mock",
            model_name=outcome.model_name,
            prompt_template_id=outcome.prompt_template_id,
            prompt_template_version=outcome.prompt_template_version,
            input_token_count=outcome.input_token_count,
            output_token_count=outcome.output_token_count,
            estimated_cost_usd=outcome.estimated_cost_usd,
            latency_ms=outcome.latency_ms,
            execution_time_ms=outcome.execution_time_ms,
            rendered_system_prompt=None,
            rendered_user_prompt=None,
            raw_response=outcome.provider_metadata,
            started_at=outcome.started_at or now,
            completed_at=outcome.completed_at,
            failure_reason=None,
            request_id=request_id,
        )
        persisted_generation_run = await self._generation_runs.add(self._session, generation_run)

        version = AIArtifactVersion(
            id=uuid.uuid4(),
            ai_artifact_id=artifact_id,
            version_number=next_version_number,
            content=outcome.content or {},
            confidence=outcome.confidence,
            source_map=outcome.source_map,
            source=AIArtifactVersionSource.AI_GENERATED,
            generation_run_id=persisted_generation_run.id,
            created_by=None,
            change_note=None,
            created_at=outcome.completed_at or now,
        )
        persisted_version = await self._artifacts.insert_version(self._session, version)

        # Una versión nueva generada por IA siempre reabre la revisión
        # humana y limpia cualquier disposición previa, incluso si la
        # anterior estaba approved/rejected — ver
        # docs/ai-pipeline-architecture.md §3.3.
        updated_artifact = await self._artifacts.update_disposition(
            self._session,
            current_user.clinic_id,
            artifact_id,
            {
                "current_version_id": persisted_version.id,
                "confidence": outcome.confidence,
                "status": AIArtifactStatus.REVIEW_PENDING.value,
                "approved_by": None,
                "approved_at": None,
                "rejected_by": None,
                "rejected_at": None,
                "rejection_reason": None,
                "updated_at": now,
            },
        )
        assert updated_artifact is not None  # se acaba de crear/confirmar en esta misma transacción

        return AIArtifactDetail(
            artifact=updated_artifact,
            current_version=persisted_version,
            generation_run=persisted_generation_run,
        )

    # --- Actualización explícita de anamnesis (Fase 6.5.3) -----------------

    async def propose_anamnesis_update(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID, request_id: str
    ) -> AnamnesisUpdateProposalOutcome:
        """Acción EXPLÍCITA disparada desde una sesión concreta — nunca
        parte de `run_pipeline`/`run_mock_pipeline` (RFC técnico de 6.5
        §0/§3 del encargo de 6.5.3). Reutiliza `get_latest_approved`
        (misma consulta longitudinal que `_resolve_patient_context`) y el
        `AIArtifact(TRANSCRIPT)` ya existente de esta sesión — nunca invoca
        un `TranscriptionProvider`."""
        clinical_session = await self._get_clinical_session_or_404(
            current_user, clinical_session_id
        )
        authorize_ai_artifact_action(
            current_user,
            AIArtifactAction.EDIT,
            professional_id=clinical_session.professional_id,
        )

        previous_artifact = await self._artifacts.get_latest_approved(
            self._session,
            current_user.clinic_id,
            clinical_session.patient_id,
            AIArtifactType.ANAMNESIS,
            exclude_clinical_session_id=clinical_session_id,
        )
        if previous_artifact is None or previous_artifact.current_version_id is None:
            raise ConflictError(
                "No existe una anamnesis aprobada previa del paciente en otra sesión; "
                "no se puede proponer una actualización."
            )
        baseline_version = await self._artifacts.get_version_by_id(
            self._session, previous_artifact.current_version_id
        )
        assert baseline_version is not None  # invariante: current_version_id ya resuelto
        assert previous_artifact.approved_at is not None  # invariante: status=APPROVED
        previous_ref = PreviousAnamnesisRef(
            artifact_id=previous_artifact.id,
            version_id=previous_artifact.current_version_id,
            clinical_session_id=previous_artifact.clinical_session_id,
            approved_at=previous_artifact.approved_at,
            content=baseline_version.content,
        )

        transcript_artifact = await self._artifacts.get_by_session_and_type(
            self._session, current_user.clinic_id, clinical_session_id, AIArtifactType.TRANSCRIPT
        )
        if transcript_artifact is None or transcript_artifact.current_version_id is None:
            raise ConflictError(
                "No existe una transcripción disponible para esta sesión; no se puede "
                "proponer una actualización de anamnesis sin un transcript."
            )
        transcript_version = await self._artifacts.get_version_by_id(
            self._session, transcript_artifact.current_version_id
        )
        assert transcript_version is not None  # invariante: current_version_id ya resuelto

        # Rerun sobre la misma sesión (RFC técnico de 6.5 §14 del encargo
        # de 6.5.3): si ya existe una propuesta B para esta sesión, su
        # baseline debe coincidir EXACTAMENTE con el baseline recién
        # resuelto — nunca rebase silencioso ni sobrescritura de
        # `baseline_*`. Si no coincide, hay que resolver B primero
        # (aprobarla/rechazarla/eliminarla) antes de regenerar.
        existing_proposal = await self._artifacts.get_by_session_and_type(
            self._session, current_user.clinic_id, clinical_session_id, AIArtifactType.ANAMNESIS
        )
        if existing_proposal is not None and (
            existing_proposal.baseline_artifact_id != previous_ref.artifact_id
            or existing_proposal.baseline_version_id != previous_ref.version_id
        ):
            raise ConflictError(
                "Ya existe una propuesta de actualización para esta sesión generada contra "
                "un baseline distinto del vigente. Resuelve la propuesta existente (apruébala, "
                "recházala o elimínala) antes de generar una nueva."
            )

        context = PipelineExecutionContext(
            clinical_session_id=clinical_session_id,
            session_context=SessionContext(
                clinical_session_id=clinical_session_id,
                session_type=clinical_session.session_type.value,
            ),
            outputs={AIArtifactType.TRANSCRIPT: transcript_version.content},
            patient_context=LoadedPatientContext(
                session_type=clinical_session.session_type.value,
                previous_approved_anamnesis=previous_ref,
            ),
        )
        step = AnamnesisUpdateStep(self._anamnesis_update_generator)
        if not step.applies_to(context):
            raise ConflictError(
                "No existe una anamnesis aprobada previa del paciente en otra sesión; "
                "no se puede proponer una actualización."
            )
        outcome = await step.run(context)

        if outcome.status == AIGenerationRunStatus.FAILED:
            raise ConflictError(
                "No se pudo generar la propuesta de actualización de anamnesis: "
                f"{outcome.failure_reason or 'error desconocido.'}"
            )

        assert outcome.content is not None  # invariante: COMPLETED siempre trae content
        changed_fields = changed_field_names(previous_ref.content, outcome.content)
        if not changed_fields:
            # RFC técnico de 6.5 §9 del encargo de 6.5.3: sin cambios reales
            # propuestos, la operación es válida pero no persiste nada — ni
            # AIArtifact, ni AIArtifactVersion, ni AIGenerationRun/AIPipelineRun.
            return AnamnesisUpdateProposalOutcome(detail=None, changed_fields=[])

        now = datetime.now(UTC)
        pipeline_run = AIPipelineRun(
            id=uuid.uuid4(),
            clinical_session_id=clinical_session_id,
            triggered_by=current_user.id,
            status=AIPipelineRunStatus.PROCESSING,
            started_at=now,
            completed_at=None,
            request_id=request_id,
        )
        try:
            persisted_run = await self._pipeline_runs.add(self._session, pipeline_run)
            detail = await self._persist_completed_outcome(
                current_user,
                persisted_run.id,
                clinical_session_id,
                outcome,
                request_id,
                baseline_artifact_id=previous_ref.artifact_id,
                baseline_version_id=previous_ref.version_id,
            )
            await self._pipeline_runs.update_fields(
                self._session,
                persisted_run.id,
                {"status": AIPipelineRunStatus.COMPLETED.value, "completed_at": datetime.now(UTC)},
            )
            await self._write_audit(
                current_user,
                request_id,
                action="ai_artifact.update_proposed",
                entity_type="ai_artifact",
                entity_id=detail.artifact.id,
                metadata={
                    "proposing_clinical_session_id": str(clinical_session_id),
                    "baseline_artifact_id": str(previous_ref.artifact_id),
                    "baseline_version_id": str(previous_ref.version_id),
                    "changed_fields": changed_fields,
                    "reasons": {
                        field_name: reason_for_previous_status(
                            AnamnesisFieldStatus(previous_ref.content[field_name]["status"])
                        ).value
                        for field_name in changed_fields
                    },
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return AnamnesisUpdateProposalOutcome(detail=detail, changed_fields=changed_fields)

    # --- Transcripción desde audio real (Fase 5) --------------------------

    async def transcribe_from_audio(
        self, current_user: CurrentUser, audio_recording_id: uuid.UUID, request_id: str
    ) -> AIArtifactDetail:
        """`Audio -> TranscriptionProvider configurado -> AIArtifact
        (transcript) -> Review` — ver docs/transcription-benchmark.md §Pipeline.

        Independiente de `run_pipeline` (Mock Pipeline): solo toca el
        artefacto `transcript` de la sesión, nunca Summary/ClinicalFlags/
        MissingInformation/Anamnesis. Reutiliza `TranscriptionStep` y
        `_persist_completed_outcome` — mismo mecanismo de versionado,
        auditoría técnica y disposición humana que el resto del pipeline.
        """
        audio_recording = await self._audio_recordings.get_by_id(
            self._session, current_user.clinic_id, audio_recording_id
        )
        if audio_recording is None:
            raise NotFoundError("Grabación de audio no encontrada.")

        clinical_session = await self._get_clinical_session_or_404(
            current_user, audio_recording.clinical_session_id
        )
        authorize_audio_recording_action(
            current_user,
            AudioRecordingAction.TRANSCRIBE,
            professional_id=clinical_session.professional_id,
        )

        if audio_recording.status not in (ProcessingStatus.READY, ProcessingStatus.TRANSCRIBED):
            raise ConflictError(
                "No se puede transcribir un audio en estado "
                f"'{audio_recording.status.value}'. Debe estar 'ready' o 'transcribed'."
            )

        existing_active = await self._pipeline_runs.get_active_for_session(
            self._session, current_user.clinic_id, audio_recording.clinical_session_id
        )
        if existing_active is not None:
            raise ConflictError("Ya existe una ejecución del pipeline en curso para esta sesión.")

        assert audio_recording.storage_reference is not None  # invariante de READY/TRANSCRIBED
        audio_bytes = await self._audio_storage.read(
            StorageReference(audio_recording.storage_reference)
        )

        settings = get_settings()
        now = datetime.now(UTC)
        pipeline_run = AIPipelineRun(
            id=uuid.uuid4(),
            clinical_session_id=audio_recording.clinical_session_id,
            triggered_by=current_user.id,
            status=AIPipelineRunStatus.PROCESSING,
            started_at=now,
            completed_at=None,
            request_id=request_id,
        )
        step = TranscriptionStep(
            self._configured_transcription_provider,
            self._token_counter,
            self._cost_estimator,
            provider_name=settings.transcription_provider,
            model_name=None,
        )
        cost_budget, retry_config, max_output_tokens_estimate = (
            await self._build_execution_guardrails(audio_recording.clinical_session_id)
        )
        context = PipelineExecutionContext(
            clinical_session_id=audio_recording.clinical_session_id,
            session_context=SessionContext(
                clinical_session_id=audio_recording.clinical_session_id,
                session_type=clinical_session.session_type.value,
            ),
            audio_input=AudioForTranscription(
                audio_bytes=audio_bytes,
                mime_type=audio_recording.mime_type,
                filename=audio_recording.original_filename,
            ),
            cost_budget=cost_budget,
            retry_config=retry_config,
            max_output_tokens_estimate=max_output_tokens_estimate,
        )

        try:
            persisted_run = await self._pipeline_runs.add(self._session, pipeline_run)
            await self._audio_recordings.update_fields(
                self._session,
                current_user.clinic_id,
                audio_recording.id,
                {"status": ProcessingStatus.TRANSCRIBING.value},
            )

            outcome = await step.run(context)

            if outcome.status == AIGenerationRunStatus.FAILED:
                await self._generation_runs.add(
                    self._session,
                    AIGenerationRun(
                        id=uuid.uuid4(),
                        ai_pipeline_run_id=persisted_run.id,
                        clinical_session_id=audio_recording.clinical_session_id,
                        artifact_type=outcome.artifact_type,
                        ai_artifact_id=None,
                        resulting_version_number=None,
                        status=outcome.status,
                        provider_name=outcome.provider_name or settings.transcription_provider,
                        model_name=outcome.model_name,
                        prompt_template_id=None,
                        prompt_template_version=None,
                        input_token_count=outcome.input_token_count,
                        output_token_count=outcome.output_token_count,
                        estimated_cost_usd=outcome.estimated_cost_usd,
                        latency_ms=outcome.latency_ms,
                        execution_time_ms=outcome.execution_time_ms,
                        rendered_system_prompt=None,
                        rendered_user_prompt=None,
                        raw_response=outcome.provider_metadata,
                        started_at=outcome.started_at or now,
                        completed_at=outcome.completed_at,
                        failure_reason=outcome.failure_reason,
                        request_id=request_id,
                    ),
                )
                await self._audio_recordings.update_fields(
                    self._session,
                    current_user.clinic_id,
                    audio_recording.id,
                    {
                        "status": ProcessingStatus.FAILED.value,
                        "failure_reason": outcome.failure_reason,
                    },
                )
                await self._pipeline_runs.update_fields(
                    self._session,
                    persisted_run.id,
                    {"status": AIPipelineRunStatus.FAILED.value, "completed_at": datetime.now(UTC)},
                )
                await self._write_audit(
                    current_user,
                    request_id,
                    action="audio_recording.transcription_failed",
                    entity_type="audio_recording",
                    entity_id=audio_recording.id,
                    metadata={"failure_reason": outcome.failure_reason},
                )
                detail = None
            else:
                detail = await self._persist_completed_outcome(
                    current_user,
                    persisted_run.id,
                    audio_recording.clinical_session_id,
                    outcome,
                    request_id,
                )
                await self._audio_recordings.update_fields(
                    self._session,
                    current_user.clinic_id,
                    audio_recording.id,
                    {"status": ProcessingStatus.TRANSCRIBED.value, "failure_reason": None},
                )
                await self._pipeline_runs.update_fields(
                    self._session,
                    persisted_run.id,
                    {
                        "status": AIPipelineRunStatus.COMPLETED.value,
                        "completed_at": datetime.now(UTC),
                    },
                )
                await self._write_audit(
                    current_user,
                    request_id,
                    action="audio_recording.transcribed",
                    entity_type="audio_recording",
                    entity_id=audio_recording.id,
                    metadata={"provider_name": outcome.provider_name},
                )

            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        if outcome.status == AIGenerationRunStatus.FAILED:
            raise ConflictError(
                "La transcripción falló: "
                f"{outcome.failure_reason or 'error desconocido del proveedor.'}"
            )

        assert detail is not None
        return detail

    # --- Lectura -----------------------------------------------------------

    async def get_artifact(
        self, current_user: CurrentUser, artifact_id: uuid.UUID
    ) -> AIArtifactDetail:
        authorize_ai_artifact_action(current_user, AIArtifactAction.READ)
        artifact = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id
        )
        if artifact is None:
            raise NotFoundError("Artefacto de IA no encontrado.")
        return await self._to_detail(artifact)

    async def list_artifacts(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID
    ) -> list[AIArtifactDetail]:
        authorize_ai_artifact_action(current_user, AIArtifactAction.READ)
        await self._get_clinical_session_or_404(current_user, clinical_session_id)
        artifacts = await self._artifacts.list_by_session(
            self._session, current_user.clinic_id, clinical_session_id
        )
        return [await self._to_detail(artifact) for artifact in artifacts]

    async def list_versions(
        self, current_user: CurrentUser, artifact_id: uuid.UUID
    ) -> list[AIArtifactVersionDetail]:
        authorize_ai_artifact_action(current_user, AIArtifactAction.READ)
        artifact = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id
        )
        if artifact is None:
            raise NotFoundError("Artefacto de IA no encontrado.")

        versions = await self._artifacts.list_versions(self._session, artifact_id)
        details: list[AIArtifactVersionDetail] = []
        for version in versions:
            generation_run = (
                await self._generation_runs.get_by_id(self._session, version.generation_run_id)
                if version.generation_run_id
                else None
            )
            details.append(
                AIArtifactVersionDetail(
                    version=version,
                    generation_run=generation_run,
                    is_current=(version.id == artifact.current_version_id),
                )
            )
        return details

    # --- Disposición humana --------------------------------------------------

    async def approve(
        self, current_user: CurrentUser, artifact_id: uuid.UUID, request_id: str
    ) -> AIArtifactDetail:
        return await self._set_disposition(
            current_user, artifact_id, request_id, action=AIArtifactAction.APPROVE
        )

    async def reject(
        self,
        current_user: CurrentUser,
        artifact_id: uuid.UUID,
        request_id: str,
        *,
        rejection_reason: str | None,
    ) -> AIArtifactDetail:
        return await self._set_disposition(
            current_user,
            artifact_id,
            request_id,
            action=AIArtifactAction.REJECT,
            rejection_reason=rejection_reason,
        )

    async def _set_disposition(
        self,
        current_user: CurrentUser,
        artifact_id: uuid.UUID,
        request_id: str,
        *,
        action: AIArtifactAction,
        rejection_reason: str | None = None,
    ) -> AIArtifactDetail:
        existing = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id
        )
        if existing is None:
            raise NotFoundError("Artefacto de IA no encontrado.")

        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, existing.clinical_session_id
        )
        assert (
            clinical_session is not None
        )  # invariante: el artefacto solo existe si la sesión existe
        authorize_ai_artifact_action(
            current_user, action, professional_id=clinical_session.professional_id
        )

        target_status = (
            AIArtifactStatus.APPROVED
            if action == AIArtifactAction.APPROVE
            else AIArtifactStatus.REJECTED
        )

        if existing.status == target_status:
            return await self._to_detail(existing)  # no-op idempotente, sin duplicar auditoría

        if existing.status != AIArtifactStatus.REVIEW_PENDING:
            raise ConflictError(
                f"No se puede {action.value} un artefacto en estado "
                f"'{existing.status.value}'. Debe volver a 'review_pending' "
                "(editando o regenerando) antes de cambiar su disposición."
            )

        # Optimistic concurrency (Hito 6.5.3, RFC técnico de 6.5 §11):
        # solo aplica a propuestas de AnamnesisUpdateStep
        # (`baseline_artifact_id is not None`) y solo al aprobar — nunca al
        # rechazar (rechazar una propuesta pendiente siempre debe poder
        # hacerse, aunque el baseline haya cambiado entre tanto). Para
        # cualquier otro artefacto (`baseline_artifact_id is None`) este
        # bloque nunca se ejecuta: comportamiento idéntico al existente.
        if action == AIArtifactAction.APPROVE and existing.baseline_artifact_id is not None:
            current_baseline = await self._artifacts.get_latest_approved(
                self._session,
                current_user.clinic_id,
                clinical_session.patient_id,
                AIArtifactType.ANAMNESIS,
                exclude_clinical_session_id=existing.clinical_session_id,
            )
            if (
                current_baseline is None
                or current_baseline.id != existing.baseline_artifact_id
                or current_baseline.current_version_id != existing.baseline_version_id
            ):
                raise ConflictError(
                    "El baseline sobre el que se generó esta propuesta de actualización ya "
                    "no es el vigente. Regenera la propuesta contra el baseline actual antes "
                    "de aprobarla."
                )

        now = datetime.now(UTC)
        values: dict[str, object] = {"status": target_status.value, "updated_at": now}
        if action == AIArtifactAction.APPROVE:
            values["approved_by"] = current_user.id
            values["approved_at"] = now
        else:
            values["rejected_by"] = current_user.id
            values["rejected_at"] = now
            values["rejection_reason"] = rejection_reason

        try:
            updated = await self._artifacts.update_disposition(
                self._session, current_user.clinic_id, artifact_id, values
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action=f"ai_artifact.{target_status.value}",
                entity_type="ai_artifact",
                entity_id=artifact_id,
                metadata=({"rejection_reason": rejection_reason} if rejection_reason else {}),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return await self._to_detail(updated)

    # --- Edición humana y borrado lógico (Fase 6, hito 6.0) --------------------

    async def edit_content(
        self,
        current_user: CurrentUser,
        artifact_id: uuid.UUID,
        request_id: str,
        *,
        content: dict,
        change_note: str | None,
    ) -> AIArtifactDetail:
        """Crea una nueva `AIArtifactVersion` con `source=HUMAN_EDITED` — ver
        docs/fase-6-rfc.md §2/§9.1. Reabre la revisión humana igual que una
        regeneración por IA (`_persist_completed_outcome`), incluso si la
        versión anterior estaba `approved`/`rejected`. Un artefacto con
        soft-delete no es editable (`get_by_id` lo excluye por defecto,
        404 antes de llegar aquí)."""
        existing = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id
        )
        if existing is None:
            raise NotFoundError("Artefacto de IA no encontrado.")

        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, existing.clinical_session_id
        )
        assert (
            clinical_session is not None
        )  # invariante: el artefacto solo existe si la sesión existe
        authorize_ai_artifact_action(
            current_user,
            AIArtifactAction.EDIT,
            professional_id=clinical_session.professional_id,
        )

        # Hito 6.1 (docs/fase-6-rfc.md §10, encargo punto 5): una edición
        # humana puede cambiar el contenido y reabrir revisión, pero nunca
        # puede romper el contrato estructural del artifact_type — a
        # diferencia de la generación automática, NO pasa por
        # `GroundingValidator`/`SafetyValidator` (pensados para confiar o
        # no en una salida de IA, no en la palabra de un profesional).
        schema_result = validate_content_schema(existing.artifact_type, content)
        if not schema_result.valid:
            raise SchemaValidationError(
                "El contenido editado no cumple el esquema de este tipo de artefacto.",
                errors=list(schema_result.errors),
            )

        now = datetime.now(UTC)
        next_version_number = (
            await self._artifacts.latest_version_number(self._session, artifact_id) + 1
        )
        version = AIArtifactVersion(
            id=uuid.uuid4(),
            ai_artifact_id=artifact_id,
            version_number=next_version_number,
            content=content,
            confidence=None,
            source_map=None,
            source=AIArtifactVersionSource.HUMAN_EDITED,
            generation_run_id=None,
            created_by=current_user.id,
            change_note=change_note,
            created_at=now,
        )

        try:
            persisted_version = await self._artifacts.insert_version(self._session, version)
            updated = await self._artifacts.update_disposition(
                self._session,
                current_user.clinic_id,
                artifact_id,
                {
                    "current_version_id": persisted_version.id,
                    "confidence": None,
                    "status": AIArtifactStatus.REVIEW_PENDING.value,
                    "approved_by": None,
                    "approved_at": None,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                    "updated_at": now,
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action="ai_artifact.human_edited",
                entity_type="ai_artifact",
                entity_id=artifact_id,
                metadata={"version_number": next_version_number},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return AIArtifactDetail(
            artifact=updated, current_version=persisted_version, generation_run=None
        )

    async def delete_artifact(
        self, current_user: CurrentUser, artifact_id: uuid.UUID, request_id: str
    ) -> None:
        """Soft-delete auditado — ver docs/fase-6-rfc.md §7.3/§9.1. No
        introduce un tercer eje de estado: `deleted_by`/`deleted_at` son
        independientes de `AIArtifactStatus` (mismo patrón que
        `AudioService.delete`, ver app/audio/service.py)."""
        existing = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id, include_deleted=True
        )
        if existing is None:
            raise NotFoundError("Artefacto de IA no encontrado.")

        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, existing.clinical_session_id
        )
        assert (
            clinical_session is not None
        )  # invariante: el artefacto solo existe si la sesión existe
        authorize_ai_artifact_action(
            current_user,
            AIArtifactAction.DELETE,
            professional_id=clinical_session.professional_id,
        )

        if existing.deleted_at is not None:
            return  # no-op idempotente

        try:
            now = datetime.now(UTC)
            updated = await self._artifacts.update_disposition(
                self._session,
                current_user.clinic_id,
                artifact_id,
                {"deleted_by": current_user.id, "deleted_at": now, "updated_at": now},
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action="ai_artifact.deleted",
                entity_type="ai_artifact",
                entity_id=artifact_id,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    # --- Helpers internos -----------------------------------------------------

    async def _build_steps(self) -> list[PipelineStep]:
        """Routing estático por `artifact_type` (Fase 6.3.7, RFC §6.1/§11.1
        decisión 12): `Settings.llm_provider_summary`/
        `llm_provider_patient_summary`/`llm_provider_missing_information`
        deciden, cada uno de forma independiente, si ese artifact_type usa
        su `Mock*Generator` inyectado (comportamiento histórico, "mock" es
        el valor por defecto en todos los entornos) o un `Real*Generator`
        con un `LanguageModelProvider` real detrás. Nunca un router
        dinámico: la decisión es 100% determinista por configuración, sin
        lectura de sesión/paciente/coste/latencia."""
        settings = get_settings()
        summary_step = await self._build_summary_step(settings)
        patient_summary_step = await self._build_patient_summary_step(settings)
        missing_information_step = await self._build_missing_information_step(settings)

        steps_by_type: dict[AIArtifactType, PipelineStep] = {
            AIArtifactType.TRANSCRIPT: self._mock_transcription_step(),
            AIArtifactType.SUMMARY: summary_step,
            AIArtifactType.PATIENT_SUMMARY: patient_summary_step,
            AIArtifactType.CLINICAL_FLAGS: self._mock_clinical_flags_step(),
            AIArtifactType.MISSING_INFORMATION: missing_information_step,
            AIArtifactType.ANAMNESIS: self._mock_anamnesis_step(),
            AIArtifactType.SESSION_NOTES: self._mock_session_notes_step(),
        }
        return [steps_by_type[artifact_type] for artifact_type in PIPELINE_STEP_ORDER]

    def _build_mock_steps(self) -> list[PipelineStep]:
        """Construye los steps EXCLUSIVAMENTE con los generators inyectados
        en el constructor (`Mock*Generator` por defecto en producción, ver
        `core/deps.py::get_ai_pipeline_service` — nunca inyecta otra cosa)
        — a diferencia de `_build_steps()`, esta función nunca lee
        `Settings.llm_provider_*`, nunca llama a
        `build_language_model_provider` y nunca resuelve una
        `PromptTemplate`. Es deliberadamente síncrona (no `async`, sin
        `await` alguno) como recordatorio de que no toca BD ni
        configuración de routing — la propiedad de seguridad exigida por
        `run_mock_pipeline` ("cero LLM externo pase lo que pase en
        Settings") depende de que este método sea así de simple y
        auditable. Si el propio llamador inyecta explícitamente un
        generator real vía el constructor de `AIPipelineService`, esa es
        una decisión de código explícita de ese llamador — no un
        interruptor de configuración por variable de entorno, que es el
        riesgo que esta función cierra."""
        steps_by_type: dict[AIArtifactType, PipelineStep] = {
            AIArtifactType.TRANSCRIPT: self._mock_transcription_step(),
            AIArtifactType.SUMMARY: SummaryStep(
                self._summary_generator, self._token_counter, self._cost_estimator
            ),
            AIArtifactType.PATIENT_SUMMARY: PatientSummaryStep(
                self._patient_summary_generator, self._token_counter, self._cost_estimator
            ),
            AIArtifactType.CLINICAL_FLAGS: self._mock_clinical_flags_step(),
            AIArtifactType.MISSING_INFORMATION: MissingInformationStep(
                self._missing_information_generator, self._token_counter, self._cost_estimator
            ),
            AIArtifactType.ANAMNESIS: self._mock_anamnesis_step(),
            AIArtifactType.SESSION_NOTES: self._mock_session_notes_step(),
        }
        return [steps_by_type[artifact_type] for artifact_type in PIPELINE_STEP_ORDER]

    def _mock_transcription_step(self) -> TranscriptionStep:
        """Construcción puramente Mock, compartida por `_build_steps()` y
        `_build_mock_steps()` (RFC técnico de 6.4, §12/§15): `TRANSCRIPT`
        no tiene routing real todavía — sin `if provider_name == "mock"`
        que factorizar, solo la llamada al constructor, antes duplicada
        byte a byte en ambos métodos."""
        return TranscriptionStep(
            self._transcription_provider, self._token_counter, self._cost_estimator
        )

    def _mock_clinical_flags_step(self) -> ClinicalFlagsStep:
        """Igual que `_mock_transcription_step`: `CLINICAL_FLAGS` es
        rule-based, nunca tiene routing LLM — ver docs/fase-6-rfc.md §4.4."""
        return ClinicalFlagsStep(
            self._clinical_flags_generator, self._token_counter, self._cost_estimator
        )

    def _mock_anamnesis_step(self) -> AnamnesisStep:
        """Igual que `_mock_transcription_step`: `ANAMNESIS` sigue sin
        routing real en 6.4.1 (RFC técnico §11 — pendiente de benchmark
        propio antes de activar un proveedor real, hito 6.4.2+)."""
        return AnamnesisStep(self._anamnesis_generator, self._token_counter, self._cost_estimator)

    def _mock_session_notes_step(self) -> SessionNotesStep:
        """Igual que `_mock_transcription_step`: `SESSION_NOTES` sigue sin
        routing real en 6.4.3 (RFC técnico §11 — misma razón que
        `ANAMNESIS`: pendiente de benchmark propio antes de activar un
        proveedor real)."""
        return SessionNotesStep(
            self._session_notes_generator, self._token_counter, self._cost_estimator
        )

    async def _build_summary_step(self, settings: Settings) -> SummaryStep:
        provider_name = settings.llm_provider_summary
        if provider_name == "mock":
            return SummaryStep(self._summary_generator, self._token_counter, self._cost_estimator)

        model = self._require_llm_model(
            settings.llm_model_summary, AIArtifactType.SUMMARY, provider_name
        )
        template = await self._require_prompt_template(AIArtifactType.SUMMARY, _DEFAULT_LANGUAGE)
        llm_provider = build_language_model_provider(settings, provider_name)
        generator = RealSummaryGenerator(llm_provider, template, model=model)
        return SummaryStep(
            generator,
            self._token_counter,
            self._llm_cost_estimator,
            provider_name=provider_name,
            model_name=model,
            prompt_template_id=template.id,
            prompt_template_version=template.version,
        )

    async def _build_patient_summary_step(self, settings: Settings) -> PatientSummaryStep:
        provider_name = settings.llm_provider_patient_summary
        if provider_name == "mock":
            return PatientSummaryStep(
                self._patient_summary_generator, self._token_counter, self._cost_estimator
            )

        model = self._require_llm_model(
            settings.llm_model_patient_summary, AIArtifactType.PATIENT_SUMMARY, provider_name
        )
        template = await self._require_prompt_template(
            AIArtifactType.PATIENT_SUMMARY, _DEFAULT_LANGUAGE
        )
        llm_provider = build_language_model_provider(settings, provider_name)
        generator = RealPatientSummaryGenerator(llm_provider, template, model=model)
        return PatientSummaryStep(
            generator,
            self._token_counter,
            self._llm_cost_estimator,
            provider_name=provider_name,
            model_name=model,
            prompt_template_id=template.id,
            prompt_template_version=template.version,
        )

    async def _build_missing_information_step(self, settings: Settings) -> MissingInformationStep:
        provider_name = settings.llm_provider_missing_information
        if provider_name == "mock":
            return MissingInformationStep(
                self._missing_information_generator, self._token_counter, self._cost_estimator
            )

        model = self._require_llm_model(
            settings.llm_model_missing_information,
            AIArtifactType.MISSING_INFORMATION,
            provider_name,
        )
        template = await self._require_prompt_template(
            AIArtifactType.MISSING_INFORMATION, _DEFAULT_LANGUAGE
        )
        llm_provider = build_language_model_provider(settings, provider_name)
        generator = RealMissingInformationGenerator(llm_provider, template, model=model)
        return MissingInformationStep(
            generator,
            self._token_counter,
            self._llm_cost_estimator,
            provider_name=provider_name,
            model_name=model,
            prompt_template_id=template.id,
            prompt_template_version=template.version,
        )

    def _require_llm_model(
        self, model: str | None, artifact_type: AIArtifactType, provider_name: str
    ) -> str:
        """Fallo de configuración explícito, nunca un `AIGenerationFailureReason`
        nuevo ni una llamada al proveedor sin modelo — mismo criterio que
        `_require_prompt_template`."""
        if not model:
            raise ConflictError(
                f"Falta configurar LLM_MODEL_{artifact_type.value.upper()} para el proveedor "
                f"'{provider_name}' de '{artifact_type.value}'."
            )
        return model

    async def _to_detail(self, artifact: AIArtifact) -> AIArtifactDetail:
        version = (
            await self._artifacts.get_version_by_id(self._session, artifact.current_version_id)
            if artifact.current_version_id
            else None
        )
        return AIArtifactDetail(artifact=artifact, current_version=version, generation_run=None)

    async def _get_clinical_session_or_404(
        self, current_user: CurrentUser, clinical_session_id: uuid.UUID
    ) -> ClinicalSession:
        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, clinical_session_id
        )
        if clinical_session is None:
            raise NotFoundError("Sesión clínica no encontrada.")
        return clinical_session

    async def _build_execution_guardrails(
        self, clinical_session_id: uuid.UUID
    ) -> tuple[SessionCostBudget | None, RetryConfig, int]:
        """Resuelve una única vez, desde `Settings`/BD, los guardarraíles
        de runtime del hito 6.1 que `PipelineExecutionContext` hace
        circular hacia `run_provider_step` — ver docs/fase-6-rfc.md §6.3.

        `cost_budget=None` (límite desactivado, valor por defecto en
        development/test) evita la consulta de coste acumulado: ni
        siquiera se toca la BD para algo que no va a bloquear nada."""
        settings = get_settings()
        cost_budget: SessionCostBudget | None = None
        if settings.llm_cost_limit_enforced:
            accumulated = await self._generation_runs.sum_estimated_cost_for_session(
                self._session, clinical_session_id
            )
            cost_budget = SessionCostBudget(
                limit_usd=settings.max_llm_cost_per_session_usd, accumulated_usd=accumulated
            )
        retry_config = RetryConfig(
            max_general_retries=settings.ai_pipeline_max_general_retries,
            max_regenerative_retries=settings.ai_pipeline_max_regenerative_retries,
            backoff_base_seconds=settings.ai_pipeline_retry_backoff_base_seconds,
        )
        return cost_budget, retry_config, settings.llm_max_output_tokens_estimate

    async def _resolve_patient_context(
        self,
        clinic_id: uuid.UUID,
        clinical_session: ClinicalSession,
        steps: list[PipelineStep],
    ) -> LoadedPatientContext:
        """Resuelve el contexto longitudinal UNA vez por *run*, antes de
        invocar al orquestador (Fase 6.4.1, RFC técnico §7/§8) — nunca lo
        resuelve el orquestador ni un `PipelineStep` por su cuenta.

        Evita la consulta cross-sesión de `get_latest_approved` por
        completo si ningún step de `steps` declaró
        `patient_context_requirements()` no vacío — inspección
        determinista y explícita de los steps ya construidos, sin
        complejidad añadida (RFC técnico §7): en 6.4.1 ningún step
        todavía declara requisitos reales, así que esta consulta nunca se
        ejecuta en producción hasta el hito 6.4.2."""
        required = _union_patient_context_requirements(steps)
        previous_anamnesis: PreviousAnamnesisRef | None = None

        if PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS in required:
            previous_artifact = await self._artifacts.get_latest_approved(
                self._session,
                clinic_id,
                clinical_session.patient_id,
                AIArtifactType.ANAMNESIS,
                exclude_clinical_session_id=clinical_session.id,
            )
            if previous_artifact is not None and previous_artifact.current_version_id is not None:
                version = await self._artifacts.get_version_by_id(
                    self._session, previous_artifact.current_version_id
                )
                if version is not None:
                    assert previous_artifact.approved_at is not None  # invariante: status=APPROVED
                    previous_anamnesis = PreviousAnamnesisRef(
                        artifact_id=previous_artifact.id,
                        version_id=previous_artifact.current_version_id,
                        clinical_session_id=previous_artifact.clinical_session_id,
                        approved_at=previous_artifact.approved_at,
                        content=version.content,
                    )

        return LoadedPatientContext(
            session_type=clinical_session.session_type.value,
            previous_approved_anamnesis=previous_anamnesis,
        )

    async def _ensure_ai_processing_consent(
        self, current_user: CurrentUser, patient_id: uuid.UUID
    ) -> None:
        """Precondición del hito 6.0 de la Fase 6 — ver
        docs/ai-pipeline-architecture.md §7.3. Con el flag desactivado
        (valor por defecto mientras `run_pipeline` solo use proveedores
        Mock) es un no-op, idéntico al comportamiento histórico."""
        settings = get_settings()
        if not settings.ai_processing_consent_enforced:
            return
        consent = await self._consents.get_latest(
            self._session, current_user.clinic_id, patient_id, ConsentType.PROCESAMIENTO_IA
        )
        if (
            consent is None
            or not consent.granted
            or consent.consent_version != settings.ai_processing_consent_version
        ):
            raise ConflictError(
                "Falta consentimiento válido de procesamiento IA para este paciente."
            )

    async def _require_prompt_template(
        self, artifact_type: AIArtifactType, language: str
    ) -> PromptTemplate:
        """Resuelve la plantilla activa **antes** de construir/ejecutar
        ningún step LLM real (Fase 6.3.3, RFC §7.4) — nunca se invoca al
        proveedor si falta la plantilla. `PipelineStep`, el `Generator` y
        `PromptRenderer` nunca reciben `self._session` ni
        `self._prompt_templates`: reciben el `PromptTemplate` ya resuelto,
        un dataclass en memoria sin conexión a BD (ver docs/fase-6-rfc.md
        §10 hito 6.1, "PipelineStep nunca accede a la base de datos").

        Un `PromptTemplateNotFoundError` es un fallo de *configuración de
        despliegue* (falta sembrar `prompt_templates`), no un fallo del
        proveedor — se traduce en `ConflictError` (mismo patrón que
        `_ensure_ai_processing_consent`), nunca en un
        `AIGenerationFailureReason` nuevo ni en un outcome `FAILED` que
        fingiera un problema del proveedor."""
        try:
            return await require_active_template(
                self._session, self._prompt_templates, artifact_type, language
            )
        except PromptTemplateNotFoundError as exc:
            raise ConflictError(
                "No hay una plantilla de prompt activa configurada para "
                f"'{artifact_type.value}/{language}' — no se puede generar sin plantilla "
                "(ejecuta el seed de prompts antes de activar este proveedor)."
            ) from exc

    async def _write_audit(
        self,
        current_user: CurrentUser,
        request_id: str,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: dict | None = None,
    ) -> None:
        await self._audit.add(
            self._session,
            AuditLogEntry(
                id=uuid.uuid4(),
                clinic_id=current_user.clinic_id,
                actor_user_id=current_user.id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
            ),
        )


def _resolve_pipeline_status(any_completed: bool, any_failed_or_skipped: bool) -> str:
    if any_completed and not any_failed_or_skipped:
        return AIPipelineRunStatus.COMPLETED.value
    if any_completed and any_failed_or_skipped:
        return AIPipelineRunStatus.PARTIALLY_FAILED.value
    return AIPipelineRunStatus.FAILED.value


def _union_patient_context_requirements(
    steps: list[PipelineStep],
) -> frozenset[PatientContextRequirement]:
    """Unión de `patient_context_requirements()` de todos los steps de
    este *run* — pura, sin I/O. Determina si `_resolve_patient_context`
    necesita tocar la base de datos en absoluto."""
    required: set[PatientContextRequirement] = set()
    for step in steps:
        required |= step.patient_context_requirements()
    return frozenset(required)


def _is_problematic_outcome(outcome: PipelineStepOutcome) -> bool:
    """`True` si un outcome con `status is None` cuenta como problema
    para `AIPipelineRunStatus` (RFC técnico de 6.4.1, Decisión final 2):
    `SKIPPED_DEPENDENCY` sí (deriva de un fallo/salto upstream, semántica
    sin cambios desde la Fase 4); `SKIPPED_NOT_APPLICABLE` nunca — el
    step simplemente no correspondía a esta sesión, no es un problema."""
    return outcome.skip_reason_code != SkipReasonCode.NOT_APPLICABLE
