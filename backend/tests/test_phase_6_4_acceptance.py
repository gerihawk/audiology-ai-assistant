"""Suite de aceptación de la Fase 6.4 (hito 6.4.5) — RFC técnico de 6.4
§1-§14 y docs/fase-6-rfc.md, Anexo A.

NO es un benchmark de calidad de modelos: cero red, cero OpenRouter, cero
Google/OpenAI/Anthropic, cero elección de modelo. Todo determinista con
dobles Mock/scripted (`tests/clinical_fixtures.py`) y pytest.

Organización (letras del encargo de 6.4.5 §2):

- Grupo 1: tabla de decisión + invariancia de session_type (A-D, M, N,
  §3, §4) — a nivel de orquestador, no BD: permite cubrir
  `session_type=None` (§4), que no puede materializarse como
  `ClinicalSession` real (dominio/BD lo declaran no-nullable).
- Grupo 2: cross-session/cross-patient/cross-clinic (E-H, §5) — contra
  Postgres real, `get_latest_approved()` nunca mockeada.
- Grupo 3: grounding ANAMNESIS + negación explícita (I, J, K, §6).
- Grupo 4: grounding SESSION_NOTES + referencia ambigua (J, K, L, §7).
- Grupo 5: estado agregado del pipeline (§8).
- Grupo 6: corrección explícita (§10) — SOLO grounding de la sesión
  actual; NO implementa `AnamnesisUpdateStep` (hito 6.5).

Deliberadamente NO duplica los tests unitarios de schema/grounding/
applies_to ya existentes en 6.4.1-6.4.4 (ver informe del hito): todos los
casos de aquí son escenarios de extremo a extremo contra
`AIPipelineService`/el orquestador real, nunca llamadas aisladas a
`validate_content_schema()` ni a `.applies_to()` en solitario.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifactType,
    AIGenerationRunStatus,
    AIPipelineRunStatus,
)
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.patient_context import (
    LoadedPatientContext,
    PreviousAnamnesisRef,
    resolve_missing_information_target,
)
from app.ai_pipeline.domain.pipeline import (
    PipelineExecutionContext,
    SequentialPipelineOrchestrator,
    SkipReasonCode,
)
from app.ai_pipeline.domain.steps.anamnesis_step import AnamnesisStep
from app.ai_pipeline.domain.steps.clinical_flags_step import ClinicalFlagsStep
from app.ai_pipeline.domain.steps.missing_information_step import MissingInformationStep
from app.ai_pipeline.domain.steps.patient_summary_step import PatientSummaryStep
from app.ai_pipeline.domain.steps.session_notes_step import SessionNotesStep
from app.ai_pipeline.domain.steps.summary_step import SummaryStep
from app.ai_pipeline.service import (
    AIPipelineService,
    _is_problematic_outcome,
    _resolve_pipeline_status,
)
from app.clinical_sessions.domain.entities import SessionType
from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus
from app.integrations.domain.missing_information_generator import MissingInformationTarget
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator
from app.integrations.mocks.mock_clinical_flags_generator import MockClinicalFlagsGenerator
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from app.integrations.mocks.mock_missing_information_generator import (
    MockMissingInformationGenerator,
)
from app.integrations.mocks.mock_patient_summary_generator import MockPatientSummaryGenerator
from app.integrations.mocks.mock_session_notes_generator import MockSessionNotesGenerator
from app.integrations.mocks.mock_summary_generator import MockSummaryGenerator
from app.integrations.mocks.mock_token_counter import MockTokenCounter
from app.patients.domain.entities import Patient
from tests.clinical_fixtures import (
    AMBIGUOUS_REFERENCE_TRANSCRIPT,
    EXPLICIT_CORRECTION_EXCERPT,
    EXPLICIT_CORRECTION_TRANSCRIPT,
    FIRST_VISIT_TRANSCRIPT,
    FOLLOW_UP_TRANSCRIPT,
    LONGITUDINAL_ONLY_PHRASE,
    EchoingSessionNotesGenerator,
    FixedTranscriptionProvider,
    ScriptedAnamnesisGenerator,
    ScriptedSessionNotesGenerator,
    anamnesis_content_with_field,
    evasive_missing_information_generator,
    session_notes_content_with_block,
)
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_clinical_session,
    create_patient,
    current_user_from,
)

# ============================================================
# Helpers compartidos
# ============================================================


def _previous_anamnesis_ref(content: dict | None = None) -> PreviousAnamnesisRef:
    return PreviousAnamnesisRef(
        artifact_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        clinical_session_id=uuid.uuid4(),
        approved_at=datetime.now(UTC),
        content=content or {},
    )


def _admin_user(clinic_with_users: ClinicWithUsers):
    return current_user_from(clinic_with_users.admin)


async def _new_session(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient_id: uuid.UUID, **overrides
):
    return await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient_id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
        **overrides,
    )


async def _run_and_approve_anamnesis(service: AIPipelineService, current_user, session_id) -> None:
    outcome = await service.run_pipeline(current_user, session_id, f"req-{uuid.uuid4()}")
    anamnesis = next(
        a for a in outcome.artifacts if a.artifact.artifact_type == AIArtifactType.ANAMNESIS
    )
    await service.approve(current_user, anamnesis.artifact.id, f"req-{uuid.uuid4()}")


async def _session_with_previous_anamnesis(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient, current_user
):
    """Crea una sesión previa con ANAMNESIS aprobada y devuelve una NUEVA
    sesión de seguimiento, lista para que SESSION_NOTES aplique."""
    previous_session = await _new_session(db_session, clinic_with_users, patient.id)
    previous_service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    await _run_and_approve_anamnesis(previous_service, current_user, previous_session.id)
    return await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )


# ============================================================
# Grupo 1: tabla de decisión + invariancia de session_type (A-D, M, N)
# ============================================================


def _decision_table_steps() -> list:
    return [
        SummaryStep(MockSummaryGenerator(), MockTokenCounter(), MockCostEstimator()),
        PatientSummaryStep(MockPatientSummaryGenerator(), MockTokenCounter(), MockCostEstimator()),
        ClinicalFlagsStep(MockClinicalFlagsGenerator(), MockTokenCounter(), MockCostEstimator()),
        MissingInformationStep(
            MockMissingInformationGenerator(), MockTokenCounter(), MockCostEstimator()
        ),
        AnamnesisStep(MockAnamnesisGenerator(), MockTokenCounter(), MockCostEstimator()),
        SessionNotesStep(MockSessionNotesGenerator(), MockTokenCounter(), MockCostEstimator()),
    ]


@pytest.mark.parametrize(
    "session_type_value,has_previous_anamnesis",
    [
        (SessionType.INITIAL_ASSESSMENT.value, False),  # A: primera visita
        (SessionType.FOLLOW_UP.value, True),  # B: follow-up con anamnesis previa
        (SessionType.HEARING_AID_FITTING.value, True),  # C: fitting con anamnesis previa
        (SessionType.HEARING_AID_FITTING.value, False),  # C bis: fitting SIN anamnesis previa
        (None, False),  # D: legacy None, sin anamnesis previa
        (None, True),  # D bis: legacy None, con anamnesis previa
    ],
)
async def test_decision_table_and_session_type_invariance(
    session_type_value: str | None, has_previous_anamnesis: bool
):
    """Verifica CONJUNTAMENTE (§3): `AnamnesisStep.applies_to()`,
    `SessionNotesStep.applies_to()`, `MissingInformationTarget` (por su
    propagación real hasta el contenido persistido, no solo la función
    pura — casos M/N), `skip_reason_code` y estado agregado del pipeline
    — los tres steps derivan del MISMO `LoadedPatientContext`, nunca de
    lecturas independientes."""
    patient_context = LoadedPatientContext(
        session_type=session_type_value,
        previous_approved_anamnesis=(_previous_anamnesis_ref() if has_previous_anamnesis else None),
    )
    context = PipelineExecutionContext(
        clinical_session_id=uuid.uuid4(),
        session_context=SessionContext(uuid.uuid4()),
        patient_context=patient_context,
    )
    context.outputs[AIArtifactType.TRANSCRIPT] = {"text": FIRST_VISIT_TRANSCRIPT, "language": "es"}

    result = await SequentialPipelineOrchestrator().run(context, _decision_table_steps())
    outcomes = {o.artifact_type: o for o in result.outcomes}

    anamnesis_outcome = outcomes[AIArtifactType.ANAMNESIS]
    session_notes_outcome = outcomes[AIArtifactType.SESSION_NOTES]
    missing_information_outcome = outcomes[AIArtifactType.MISSING_INFORMATION]

    if has_previous_anamnesis:
        assert anamnesis_outcome.status is None
        assert anamnesis_outcome.skip_reason_code == SkipReasonCode.NOT_APPLICABLE
        assert session_notes_outcome.status == AIGenerationRunStatus.COMPLETED
        expected_topics = {"device_adjustments", "next_steps"}  # N
    else:
        assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED
        assert session_notes_outcome.status is None
        assert session_notes_outcome.skip_reason_code == SkipReasonCode.NOT_APPLICABLE
        expected_topics = {"antecedentes_familiares", "exposicion_ruido"}  # M

    assert missing_information_outcome.status == AIGenerationRunStatus.COMPLETED
    actual_topics = {item["topic"] for item in missing_information_outcome.content["items"]}
    assert actual_topics == expected_topics

    # session_type nunca determina applies_to()/target (§4).
    assert resolve_missing_information_target(context.patient_context) == (
        MissingInformationTarget.SESSION_NOTES_BLOCKS
        if has_previous_anamnesis
        else MissingInformationTarget.ANAMNESIS_FIELDS
    )

    # Estado agregado (§8, "caso sano con NOT_APPLICABLE → COMPLETED"),
    # reutilizando la lógica REAL de agregación de service.py.
    any_completed = any(o.status == AIGenerationRunStatus.COMPLETED for o in result.outcomes)
    any_problematic = any(
        (o.status == AIGenerationRunStatus.FAILED)
        or (o.status is None and _is_problematic_outcome(o))
        for o in result.outcomes
    )
    assert _resolve_pipeline_status(any_completed, any_problematic) == (
        AIPipelineRunStatus.COMPLETED.value
    )


# ============================================================
# Grupo 2: cross-session / cross-patient / cross-clinic (E-H)
# ============================================================


async def test_current_session_never_counts_as_its_own_previous_anamnesis(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso F — Decisión final 1 del RFC técnico de 6.4.1: reprocesar la
    MISMA sesión tras aprobar su propia anamnesis no debe convertirla en
    su propio caso SESSION_NOTES."""
    current_user = _admin_user(clinic_with_users)
    session = await _new_session(db_session, clinic_with_users, patient.id)
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    await _run_and_approve_anamnesis(service, current_user, session.id)

    second_run = await service.run_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")

    anamnesis_outcome = next(
        o for o in second_run.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED


async def test_other_patient_anamnesis_never_leaks_into_pipeline_decision(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    """Caso G."""
    current_user = _admin_user(clinic_with_users)
    patient_a = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    patient_b = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )

    session_a = await _new_session(db_session, clinic_with_users, patient_a.id)
    await _run_and_approve_anamnesis(service, current_user, session_a.id)

    session_b = await _new_session(db_session, clinic_with_users, patient_b.id)
    result_b = await service.run_pipeline(current_user, session_b.id, f"req-{uuid.uuid4()}")

    anamnesis_outcome = next(
        o for o in result_b.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED


async def test_other_clinic_anamnesis_never_leaks_into_pipeline_decision(db_session: AsyncSession):
    """Caso H."""
    clinic_1 = await create_clinic_with_users(db_session)
    clinic_2 = await create_clinic_with_users(db_session)
    patient_1 = await create_patient(db_session, clinic_1.clinic.id, clinic_1.admin.id)
    patient_2 = await create_patient(db_session, clinic_2.clinic.id, clinic_2.admin.id)

    service_1 = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    session_1 = await create_clinical_session(
        db_session, clinic_1.clinic.id, patient_1.id, clinic_1.audiologist.id, clinic_1.admin.id
    )
    await _run_and_approve_anamnesis(service_1, _admin_user(clinic_1), session_1.id)

    service_2 = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    session_2 = await create_clinical_session(
        db_session, clinic_2.clinic.id, patient_2.id, clinic_2.audiologist.id, clinic_2.admin.id
    )
    result_2 = await service_2.run_pipeline(
        _admin_user(clinic_2), session_2.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_outcome = next(
        o for o in result_2.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED


async def test_previous_anamnesis_content_propagates_to_session_notes_generator(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso E, con prueba de propagación real de contenido — más allá de
    "qué fila de la query gana", ya probado exhaustivamente a nivel de
    repositorio en 6.4.1 (`test_ai_pipeline_artifact_repository.py`,
    incluida "varias aprobadas → gana `approved_at` más reciente", no
    reproducido aquí para no duplicar): el `previous_anamnesis_context`
    que recibe `SessionNotesGenerator` debe contener el valor real de la
    anamnesis aprobada, no un placeholder vacío."""
    current_user = _admin_user(clinic_with_users)
    marker_value = "Acúfenos referidos, marcador de contenido previo único."
    first_session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted_anamnesis = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus",
            value=marker_value,
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt="acúfenos",
        )
    )
    first_service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_generator=scripted_anamnesis,
    )
    await _run_and_approve_anamnesis(first_service, current_user, first_session.id)

    second_session = await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )
    echo_generator = EchoingSessionNotesGenerator(
        block_name="changes_since_last_visit", current_transcript_excerpt="ha mejorado"
    )
    second_service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FOLLOW_UP_TRANSCRIPT),
        session_notes_generator=echo_generator,
    )
    second_run = await second_service.run_pipeline(
        current_user, second_session.id, f"req-{uuid.uuid4()}"
    )

    session_notes_artifact = next(
        a for a in second_run.artifacts if a.artifact.artifact_type == AIArtifactType.SESSION_NOTES
    )
    persisted_text = session_notes_artifact.current_version.content["changes_since_last_visit"][
        "text"
    ]
    assert marker_value in persisted_text


# ============================================================
# Grupo 3: grounding ANAMNESIS + negación explícita (I, J, K)
# ============================================================


async def test_anamnesis_informado_con_excerpt_literal_es_valido_de_extremo_a_extremo(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso J."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus",
            value="Acúfenos en oído izquierdo.",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt="acúfenos en el oído izquierdo",
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_generator=scripted,
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED
    assert anamnesis_outcome.content["tinnitus"]["status"] == "informado"


async def test_anamnesis_negado_explicitamente_con_excerpt_literal_es_valido(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso I (negación explícita) — con el Mock de producción real (no
    scripted), sobre el transcript de primera visita que ya contiene
    "Niega vértigo" (regla de seguridad clínica: nunca informado/negado
    sin cita — docs/clinical-safety.md §6)."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_artifact = next(
        a for a in outcome.artifacts if a.artifact.artifact_type == AIArtifactType.ANAMNESIS
    )
    negated_field = anamnesis_artifact.current_version.content["vertigo_o_inestabilidad"]
    assert negated_field["status"] == "negado_explicitamente"
    assert negated_field["source_excerpt"]
    assert negated_field["source_excerpt"].lower() in FIRST_VISIT_TRANSCRIPT.lower()


@pytest.mark.parametrize(
    "field_status,source_excerpt",
    [
        (AnamnesisFieldStatus.INFORMADO, None),
        (AnamnesisFieldStatus.NO_PREGUNTADO, "cita inventada para un campo no explorado"),
    ],
)
async def test_anamnesis_combinaciones_invalidas_fallan_schema_de_extremo_a_extremo(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    field_status: AnamnesisFieldStatus,
    source_excerpt: str | None,
):
    """Caso K (parte 1: ausencia/exceso de excerpt) — de extremo a
    extremo contra el pipeline real; la exhaustividad de las 4
    combinaciones vive en 6.4.2 (`test_ai_pipeline_schemas.py`), no
    reproducida aquí."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus", value="x", status=field_status, source_excerpt=source_excerpt
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_generator=scripted,
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.FAILED
    assert (
        anamnesis_outcome.failure_reason == AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED.value
    )


async def test_anamnesis_excerpt_ausente_del_transcript_actual_falla_grounding(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso K (parte 2: excerpt falso). ANAMNESIS nunca recibe contexto
    longitudinal (solo corre cuando NO existe anamnesis previa, por
    definición de `applies_to()`) — `LONGITUDINAL_ONLY_PHRASE` aquí solo
    representa "cualquier texto ausente del transcript actual"."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus",
            value="x",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt=LONGITUDINAL_ONLY_PHRASE,
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_generator=scripted,
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.FAILED
    assert anamnesis_outcome.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED.value


# ============================================================
# Grupo 4: grounding SESSION_NOTES + referencia ambigua (J, K, L)
# ============================================================


async def test_session_notes_texto_con_excerpt_literal_es_valido_de_extremo_a_extremo(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso J (SESSION_NOTES)."""
    current_user = _admin_user(clinic_with_users)
    follow_up_session = await _session_with_previous_anamnesis(
        db_session, clinic_with_users, patient, current_user
    )
    scripted = ScriptedSessionNotesGenerator(
        blocks=session_notes_content_with_block(
            "device_adjustments", text="Ajuste realizado.", source_excerpt="ajustamos el volumen"
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FOLLOW_UP_TRANSCRIPT),
        session_notes_generator=scripted,
    )

    outcome = await service.run_pipeline(current_user, follow_up_session.id, f"req-{uuid.uuid4()}")

    session_notes_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.SESSION_NOTES
    )
    assert session_notes_outcome.status == AIGenerationRunStatus.COMPLETED


async def test_session_notes_excerpt_solo_en_contexto_longitudinal_falla_grounding(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Caso L — un excerpt que solo existiría en contexto longitudinal
    (nunca en el transcript de la sesión actual) nunca satisface el
    grounding actual. `AMBIGUOUS_REFERENCE_TRANSCRIPT` no contiene
    `LONGITUDINAL_ONLY_PHRASE` en absoluto."""
    current_user = _admin_user(clinic_with_users)
    follow_up_session = await _session_with_previous_anamnesis(
        db_session, clinic_with_users, patient, current_user
    )
    scripted = ScriptedSessionNotesGenerator(
        blocks=session_notes_content_with_block(
            "device_adjustments",
            text="Referencia ambigua a algo comentado antes.",
            source_excerpt=LONGITUDINAL_ONLY_PHRASE,
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(AMBIGUOUS_REFERENCE_TRANSCRIPT),
        session_notes_generator=scripted,
    )

    outcome = await service.run_pipeline(current_user, follow_up_session.id, f"req-{uuid.uuid4()}")

    session_notes_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.SESSION_NOTES
    )
    assert session_notes_outcome.status == AIGenerationRunStatus.FAILED
    assert session_notes_outcome.failure_reason == AIGenerationFailureReason.GROUNDING_FAILED.value


async def test_session_notes_bloque_vacio_es_valido_de_extremo_a_extremo(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """text="" + source_excerpt=None → válido (§7). Usa el Mock de
    producción real: ninguna keyword coincide con
    `AMBIGUOUS_REFERENCE_TRANSCRIPT`, así que los 4 bloques quedan
    vacíos de forma natural."""
    current_user = _admin_user(clinic_with_users)
    follow_up_session = await _session_with_previous_anamnesis(
        db_session, clinic_with_users, patient, current_user
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(AMBIGUOUS_REFERENCE_TRANSCRIPT),
    )

    outcome = await service.run_pipeline(current_user, follow_up_session.id, f"req-{uuid.uuid4()}")

    session_notes_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.SESSION_NOTES
    )
    assert session_notes_outcome.status == AIGenerationRunStatus.COMPLETED
    assert all(
        block == {"text": "", "source_excerpt": None}
        for block in session_notes_outcome.content.values()
    )


async def test_session_notes_texto_vacio_con_excerpt_es_invalido_de_extremo_a_extremo(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """text="" + source_excerpt!=None → schema inválido (§7)."""
    current_user = _admin_user(clinic_with_users)
    follow_up_session = await _session_with_previous_anamnesis(
        db_session, clinic_with_users, patient, current_user
    )
    scripted = ScriptedSessionNotesGenerator(
        blocks=session_notes_content_with_block(
            "next_steps", text="", source_excerpt="cita inventada para bloque vacío"
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FOLLOW_UP_TRANSCRIPT),
        session_notes_generator=scripted,
    )

    outcome = await service.run_pipeline(current_user, follow_up_session.id, f"req-{uuid.uuid4()}")

    session_notes_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.SESSION_NOTES
    )
    assert session_notes_outcome.status == AIGenerationRunStatus.FAILED
    assert (
        session_notes_outcome.failure_reason
        == AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED.value
    )


# ============================================================
# Grupo 5: estado agregado del pipeline (§8)
# ============================================================


async def test_fallo_real_en_anamnesis_produce_partially_failed_sin_que_not_applicable_lo_agrave(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Combina "fallo real" (ANAMNESIS FAILED por grounding) con
    "NOT_APPLICABLE nunca degrada" (SESSION_NOTES se salta en la MISMA
    ejecución sin sumar al problema) — RFC técnico de 6.4.1, Decisión
    final 2."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus",
            value="x",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt=LONGITUDINAL_ONLY_PHRASE,
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_generator=scripted,
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.pipeline_run.status == AIPipelineRunStatus.PARTIALLY_FAILED
    outcomes_by_type = {o.artifact_type: o for o in outcome.outcomes}
    assert outcomes_by_type[AIArtifactType.ANAMNESIS].status == AIGenerationRunStatus.FAILED
    assert outcomes_by_type[AIArtifactType.SESSION_NOTES].skip_reason_code == (
        SkipReasonCode.NOT_APPLICABLE
    )
    assert outcomes_by_type[AIArtifactType.SUMMARY].status == AIGenerationRunStatus.COMPLETED


async def test_skipped_dependency_derivado_de_un_fallo_real_sigue_siendo_problematico(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """MISSING_INFORMATION falla (respuesta evasiva determinista) →
    ANAMNESIS se salta como SKIPPED_DEPENDENCY (depende de
    MISSING_INFORMATION) — a diferencia de NOT_APPLICABLE, SÍ cuenta como
    problema para el estado agregado."""
    session = await _new_session(db_session, clinic_with_users, patient.id)
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        missing_information_generator=evasive_missing_information_generator(),
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.pipeline_run.status == AIPipelineRunStatus.PARTIALLY_FAILED
    outcomes_by_type = {o.artifact_type: o for o in outcome.outcomes}
    assert outcomes_by_type[AIArtifactType.MISSING_INFORMATION].status == (
        AIGenerationRunStatus.FAILED
    )
    assert outcomes_by_type[AIArtifactType.MISSING_INFORMATION].failure_reason == (
        AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE.value
    )
    assert outcomes_by_type[AIArtifactType.ANAMNESIS].skip_reason_code == (
        SkipReasonCode.DEPENDENCY_FAILED_OR_SKIPPED
    )
    # SESSION_NOTES no depende de MISSING_INFORMATION (solo de TRANSCRIPT):
    # se saltó por NOT_APPLICABLE (primera visita), no por dependencia.
    assert outcomes_by_type[AIArtifactType.SESSION_NOTES].skip_reason_code == (
        SkipReasonCode.NOT_APPLICABLE
    )


# ============================================================
# Grupo 6: corrección explícita (§10) — SOLO grounding de la sesión
# actual. NO implementa AnamnesisUpdateStep (diferido a 6.5): esta
# transcripción no interactúa con ninguna anamnesis previa.
# ============================================================


async def test_correccion_explicita_de_la_sesion_actual_es_evidencia_valida(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    session = await _new_session(db_session, clinic_with_users, patient.id)
    scripted = ScriptedAnamnesisGenerator(
        fields=anamnesis_content_with_field(
            "tinnitus",
            value="Pitido leve en oído derecho desde hace una semana (corrección del paciente).",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt=EXPLICIT_CORRECTION_EXCERPT,
        )
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(EXPLICIT_CORRECTION_TRANSCRIPT),
        anamnesis_generator=scripted,
    )

    outcome = await service.run_pipeline(
        _admin_user(clinic_with_users), session.id, f"req-{uuid.uuid4()}"
    )

    anamnesis_outcome = next(
        o for o in outcome.outcomes if o.artifact_type == AIArtifactType.ANAMNESIS
    )
    assert anamnesis_outcome.status == AIGenerationRunStatus.COMPLETED
    assert anamnesis_outcome.content["tinnitus"]["status"] == "informado"
