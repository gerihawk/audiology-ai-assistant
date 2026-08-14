"""Suite de aceptación del Hito 6.5.3 — `AnamnesisUpdateStep` + persistencia
de propuesta + optimistic concurrency (encargo §16-§17). Contra Postgres
real de test, con dobles Mock/scripted (`tests/clinical_fixtures.py`),
cero red, cero proveedor real.

Organización:

- Grupo 1 (P1-P11): persistencia, baseline visible durante review_pending,
  optimistic concurrency, rerun, aislamiento.
- Grupo 2 (A-K): `AnamnesisUpdateStep`/endpoint — baseline ausente,
  fills_gap/explicit_correction persistidos, grounding acotado, lista
  vacía, permiso, frontera con run-pipeline/run-mock-pipeline, forma del
  documento persistido.
- Grupo 3: regresión de `edit_content` sobre una propuesta (baseline_*
  no debe alterarse).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactStatus, AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.ai_pipeline.service import AIPipelineService
from app.clinical_sessions.domain.entities import ClinicalSession, SessionType
from app.core.exceptions import ConflictError
from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus
from app.integrations.domain.anamnesis_update_generator import (
    AnamnesisFieldUpdate,
    AnamnesisUpdateReason,
)
from app.patients.domain.entities import Patient
from tests.clinical_fixtures import (
    CORRECTED_VALUE_TRANSCRIPT,
    EXPLICIT_CORRECTION_TRANSCRIPT,
    FIRST_VISIT_TRANSCRIPT,
    LONGITUDINAL_ONLY_PHRASE,
    FixedTranscriptionProvider,
    ScriptedAnamnesisUpdateGenerator,
)
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_clinical_session,
    create_patient,
    current_user_from,
    dev_headers,
)

_REPO = SqlAlchemyAIArtifactRepository()


def _admin_user(clinic_with_users: ClinicWithUsers):
    return current_user_from(clinic_with_users.admin)


async def _new_session(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient_id: uuid.UUID, **overrides
) -> ClinicalSession:
    return await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient_id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
        **overrides,
    )


async def _approve_baseline_anamnesis(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient_id: uuid.UUID,
    current_user,
):
    """Sesión previa con ANAMNESIS aprobada (vía `run_mock_pipeline` +
    `approve`, real de extremo a extremo) — devuelve `(session, detail)`."""
    session = await _new_session(db_session, clinic_with_users, patient_id)
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    outcome = await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")
    anamnesis = next(
        a for a in outcome.artifacts if a.artifact.artifact_type == AIArtifactType.ANAMNESIS
    )
    detail = await service.approve(current_user, anamnesis.artifact.id, f"req-{uuid.uuid4()}")
    return session, detail


async def _session_with_transcript(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient_id: uuid.UUID,
    current_user,
    transcript_text: str,
    **session_overrides,
) -> tuple[ClinicalSession, AIPipelineService]:
    session = await _new_session(db_session, clinic_with_users, patient_id, **session_overrides)
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(transcript_text)
    )
    await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")
    return session, service


# ============================================================
# Grupo 1: persistencia (P1-P11)
# ============================================================


async def test_p1_generate_b_persists_review_pending_with_baseline_identity(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    baseline_session, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    current_session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    third_session = await _new_session(db_session, clinic_with_users, patient.id)

    outcome = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.detail is not None
    b_artifact = outcome.detail.artifact
    assert b_artifact.status == AIArtifactStatus.REVIEW_PENDING
    assert b_artifact.clinical_session_id == current_session.id
    assert b_artifact.baseline_artifact_id == baseline_detail.artifact.id
    assert b_artifact.baseline_version_id == baseline_detail.artifact.current_version_id

    # A intacta.
    reloaded_a = await _REPO.get_by_id(
        db_session, clinic_with_users.clinic.id, baseline_detail.artifact.id
    )
    assert reloaded_a is not None
    assert reloaded_a.status == AIArtifactStatus.APPROVED
    assert reloaded_a.current_version_id == baseline_detail.artifact.current_version_id

    still_a = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=third_session.id,
    )
    assert still_a is not None
    assert still_a.id == baseline_detail.artifact.id


async def test_p2_reject_b_keeps_a_as_baseline(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    current_session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    third_session = await _new_session(db_session, clinic_with_users, patient.id)
    outcome = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )

    await service.reject(
        current_user, outcome.detail.artifact.id, f"req-{uuid.uuid4()}", rejection_reason=None
    )

    still_a = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=third_session.id,
    )
    assert still_a is not None
    assert still_a.id == baseline_detail.artifact.id


async def test_p3_approve_b_makes_it_the_new_baseline(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    current_session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    third_session = await _new_session(db_session, clinic_with_users, patient.id)
    outcome = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )

    approved = await service.approve(
        current_user, outcome.detail.artifact.id, f"req-{uuid.uuid4()}"
    )
    assert approved.artifact.status == AIArtifactStatus.APPROVED

    now_b = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=third_session.id,
    )
    assert now_b is not None
    assert now_b.id == outcome.detail.artifact.id


async def test_p4_b_pending_and_c_from_another_session_coexist(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)

    session_b, service_b = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome_b = await service_b.propose_anamnesis_update(
        current_user, session_b.id, f"req-{uuid.uuid4()}"
    )

    session_c, service_c = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        EXPLICIT_CORRECTION_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome_c = await service_c.propose_anamnesis_update(
        current_user, session_c.id, f"req-{uuid.uuid4()}"
    )

    assert outcome_b.detail is not None
    assert outcome_c.detail is not None
    assert outcome_b.detail.artifact.id != outcome_c.detail.artifact.id
    assert outcome_b.detail.artifact.status == AIArtifactStatus.REVIEW_PENDING
    assert outcome_c.detail.artifact.status == AIArtifactStatus.REVIEW_PENDING


async def test_p5_approving_b_then_c_yields_stale_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)

    session_b, service_b = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome_b = await service_b.propose_anamnesis_update(
        current_user, session_b.id, f"req-{uuid.uuid4()}"
    )

    session_c, service_c = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        EXPLICIT_CORRECTION_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome_c = await service_c.propose_anamnesis_update(
        current_user, session_c.id, f"req-{uuid.uuid4()}"
    )

    await service_b.approve(current_user, outcome_b.detail.artifact.id, f"req-{uuid.uuid4()}")

    try:
        await service_c.approve(current_user, outcome_c.detail.artifact.id, f"req-{uuid.uuid4()}")
        raise AssertionError("se esperaba ConflictError por baseline obsoleto")
    except ConflictError:
        pass

    c_reloaded = await _REPO.get_by_id(
        db_session, clinic_with_users.clinic.id, outcome_c.detail.artifact.id
    )
    assert c_reloaded is not None
    assert c_reloaded.status == AIArtifactStatus.REVIEW_PENDING

    third_session = await _new_session(db_session, clinic_with_users, patient.id)
    winner = await _REPO.get_latest_approved(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        AIArtifactType.ANAMNESIS,
        exclude_clinical_session_id=third_session.id,
    )
    assert winner is not None
    assert winner.id == outcome_b.detail.artifact.id


async def test_p6_human_edit_of_b_preserves_baseline_identity(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    current_session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )
    edited_content = dict(outcome.detail.current_version.content)

    edited = await service.edit_content(
        current_user,
        outcome.detail.artifact.id,
        f"req-{uuid.uuid4()}",
        content=edited_content,
        change_note="ajuste humano",
    )

    assert edited.current_version.version_number == 2
    assert edited.artifact.baseline_artifact_id == baseline_detail.artifact.id
    assert edited.artifact.baseline_version_id == baseline_detail.artifact.current_version_id


async def test_p7_rerun_same_session_same_baseline_versions_the_same_artifact(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    current_session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    first = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )
    second = await service.propose_anamnesis_update(
        current_user, current_session.id, f"req-{uuid.uuid4()}"
    )

    assert first.detail is not None and second.detail is not None
    assert first.detail.artifact.id == second.detail.artifact.id
    assert second.detail.current_version.version_number == 2
    assert second.detail.artifact.baseline_artifact_id == first.detail.artifact.baseline_artifact_id
    assert second.detail.artifact.baseline_version_id == first.detail.artifact.baseline_version_id


async def test_p8_rerun_same_session_after_baseline_changed_conflicts(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)

    session_b, service_b = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    first_on_b = await service_b.propose_anamnesis_update(
        current_user, session_b.id, f"req-{uuid.uuid4()}"
    )

    # Otra sesión propone y aprueba una actualización distinta contra el
    # MISMO baseline A — desplaza a A como baseline vigente del paciente.
    session_c, service_c = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        EXPLICIT_CORRECTION_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome_c = await service_c.propose_anamnesis_update(
        current_user, session_c.id, f"req-{uuid.uuid4()}"
    )
    await service_c.approve(current_user, outcome_c.detail.artifact.id, f"req-{uuid.uuid4()}")

    try:
        await service_b.propose_anamnesis_update(current_user, session_b.id, f"req-{uuid.uuid4()}")
        raise AssertionError("se esperaba ConflictError por baseline distinto al vigente")
    except ConflictError:
        pass

    # Sin rebase silencioso: B sigue exactamente como tras el primer run.
    b_reloaded = await _REPO.get_by_id(
        db_session, clinic_with_users.clinic.id, first_on_b.detail.artifact.id
    )
    assert b_reloaded is not None
    assert b_reloaded.baseline_artifact_id == first_on_b.detail.artifact.baseline_artifact_id
    versions = await _REPO.list_versions(db_session, first_on_b.detail.artifact.id)
    assert len(versions) == 1


async def test_p9_regular_artifact_approve_reject_edit_unaffected(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    """Artefacto sin `baseline_*` (p. ej. SUMMARY) — comprobación de
    staleness nunca se ejecuta, comportamiento idéntico al existente."""
    current_user = _admin_user(clinic_with_users)
    session = await _new_session(db_session, clinic_with_users, patient.id)
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )
    outcome = await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")
    summary = next(
        a for a in outcome.artifacts if a.artifact.artifact_type == AIArtifactType.SUMMARY
    )
    assert summary.artifact.baseline_artifact_id is None
    assert summary.artifact.baseline_version_id is None

    approved = await service.approve(current_user, summary.artifact.id, f"req-{uuid.uuid4()}")
    assert approved.artifact.status == AIArtifactStatus.APPROVED


async def test_p10_cross_patient_isolation(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    other_patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    await _approve_baseline_anamnesis(db_session, clinic_with_users, other_patient.id, current_user)

    current_session, service = await _session_with_transcript(
        db_session, clinic_with_users, patient.id, current_user, CORRECTED_VALUE_TRANSCRIPT
    )

    try:
        await service.propose_anamnesis_update(
            current_user, current_session.id, f"req-{uuid.uuid4()}"
        )
        raise AssertionError("se esperaba ConflictError: sin baseline para este paciente")
    except ConflictError:
        pass


async def test_p11_cross_clinic_isolation(db_session: AsyncSession):
    clinic_a = await create_clinic_with_users(db_session)
    clinic_b = await create_clinic_with_users(db_session)
    patient_a = await create_patient(db_session, clinic_a.clinic.id, clinic_a.admin.id)
    patient_b = await create_patient(db_session, clinic_b.clinic.id, clinic_b.admin.id)

    await _approve_baseline_anamnesis(
        db_session, clinic_a, patient_a.id, current_user_from(clinic_a.admin)
    )

    current_user_b = current_user_from(clinic_b.admin)
    current_session, service = await _session_with_transcript(
        db_session, clinic_b, patient_b.id, current_user_b, CORRECTED_VALUE_TRANSCRIPT
    )

    try:
        await service.propose_anamnesis_update(
            current_user_b, current_session.id, f"req-{uuid.uuid4()}"
        )
        raise AssertionError("se esperaba ConflictError: sin baseline en esta clínica")
    except ConflictError:
        pass


# ============================================================
# Grupo 2: AnamnesisUpdateStep / endpoint (A-K)
# ============================================================


async def test_a_no_baseline_raises_conflict(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    session, service = await _session_with_transcript(
        db_session, clinic_with_users, patient.id, current_user, FIRST_VISIT_TRANSCRIPT
    )

    try:
        await service.propose_anamnesis_update(current_user, session.id, f"req-{uuid.uuid4()}")
        raise AssertionError("se esperaba ConflictError: sin anamnesis previa aprobada")
    except ConflictError:
        pass


async def test_b_fills_gap_proposal_is_persisted(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.detail is not None
    assert "otalgia" in outcome.changed_fields
    assert outcome.detail.current_version.content["otalgia"]["status"] == "informado"


async def test_c_explicit_correction_proposal_is_persisted(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        EXPLICIT_CORRECTION_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.detail is not None
    assert "tinnitus" in outcome.changed_fields
    assert outcome.detail.current_version.content["tinnitus"]["status"] == "informado"


async def test_d_fabricated_excerpt_grounding_failure_persists_nothing(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    tinnitus_baseline = baseline_detail.current_version.content["tinnitus"]
    fabricated = AnamnesisFieldUpdate(
        field_name="tinnitus",
        previous_value=tinnitus_baseline["value"],
        previous_status=AnamnesisFieldStatus(tinnitus_baseline["status"]),
        proposed_value="Corrección inventada.",
        proposed_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
        source_excerpt="una frase que no existe en ningún transcript de este test",
        reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
    )
    session = await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_update_generator=ScriptedAnamnesisUpdateGenerator([fabricated]),
    )
    await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")

    try:
        await service.propose_anamnesis_update(current_user, session.id, f"req-{uuid.uuid4()}")
        raise AssertionError("se esperaba ConflictError por grounding_failed")
    except ConflictError:
        pass

    persisted = (
        await service._artifacts.get_by_session_and_type(  # noqa: SLF001 - verificación directa
            db_session, clinic_with_users.clinic.id, session.id, AIArtifactType.ANAMNESIS
        )
    )
    assert persisted is None


async def test_e_longitudinal_only_excerpt_grounding_failure_persists_nothing(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    tinnitus_baseline = baseline_detail.current_version.content["tinnitus"]
    longitudinal_only = AnamnesisFieldUpdate(
        field_name="tinnitus",
        previous_value=tinnitus_baseline["value"],
        previous_status=AnamnesisFieldStatus(tinnitus_baseline["status"]),
        proposed_value="Corrección basada en contexto previo.",
        proposed_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
        source_excerpt=LONGITUDINAL_ONLY_PHRASE,
        reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
    )
    session = await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )
    service = AIPipelineService(
        db_session,
        transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT),
        anamnesis_update_generator=ScriptedAnamnesisUpdateGenerator([longitudinal_only]),
    )
    await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")

    try:
        await service.propose_anamnesis_update(current_user, session.id, f"req-{uuid.uuid4()}")
        raise AssertionError("se esperaba ConflictError por grounding_failed")
    except ConflictError:
        pass

    persisted = (
        await service._artifacts.get_by_session_and_type(  # noqa: SLF001 - verificación directa
            db_session, clinic_with_users.clinic.id, session.id, AIArtifactType.ANAMNESIS
        )
    )
    assert persisted is None


async def test_f_no_changes_proposed_creates_nothing(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        FIRST_VISIT_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )

    assert outcome.detail is None
    assert outcome.changed_fields == []
    persisted = await _REPO.get_by_session_and_type(
        db_session, clinic_with_users.clinic.id, session.id, AIArtifactType.ANAMNESIS
    )
    assert persisted is None


async def test_g_endpoint_requires_edit_permission(
    api_client: AsyncClient, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    admin_user = current_user_from(clinic_with_users.admin)
    patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, admin_user)

    session_response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": str(patient.id),
            "professional_id": str(clinic_with_users.admin.id),
            "session_type": "follow_up",
            "status": "completed",
        },
        headers=dev_headers(clinic_with_users.admin),
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["id"]
    run_response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/run-mock-pipeline",
        headers=dev_headers(clinic_with_users.admin),
    )
    assert run_response.status_code == 201, run_response.text

    viewer_response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/propose-anamnesis-update",
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert viewer_response.status_code == 403

    non_owner_response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/propose-anamnesis-update",
        headers=dev_headers(clinic_with_users.audiologist),
    )
    assert non_owner_response.status_code == 403

    admin_response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/propose-anamnesis-update",
        headers=dev_headers(clinic_with_users.admin),
    )
    # Permiso concedido (no 403) — el contenido puede legítimamente ser
    # "no changes proposed" aquí: tanto el baseline como la sesión actual
    # usan el mismo transcript fijo de `MockTranscriptionProvider` (la API
    # no permite inyectar `FixedTranscriptionProvider`), así que no hay
    # huecos ni marcadores de corrección que disparen un cambio. Este test
    # verifica el PERMISO, no el contenido — ver test_b/test_c/test_f para
    # el contenido de la propuesta.
    assert admin_response.status_code == 200, admin_response.text


async def test_h_run_pipeline_never_executes_anamnesis_update_step(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session = await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )

    outcome = await service.run_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")

    artifact_types = {a.artifact.artifact_type for a in outcome.artifacts}
    assert AIArtifactType.ANAMNESIS not in artifact_types
    assert AIArtifactType.SESSION_NOTES in artifact_types


async def test_i_run_mock_pipeline_never_executes_anamnesis_update_step(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session = await _new_session(
        db_session, clinic_with_users, patient.id, session_type=SessionType.FOLLOW_UP
    )
    service = AIPipelineService(
        db_session, transcription_provider=FixedTranscriptionProvider(FIRST_VISIT_TRANSCRIPT)
    )

    outcome = await service.run_mock_pipeline(current_user, session.id, f"req-{uuid.uuid4()}")

    artifact_types = {a.artifact.artifact_type for a in outcome.artifacts}
    assert AIArtifactType.ANAMNESIS not in artifact_types
    assert AIArtifactType.SESSION_NOTES in artifact_types


async def test_j_persisted_source_map_contains_only_modified_fields(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    await _approve_baseline_anamnesis(db_session, clinic_with_users, patient.id, current_user)
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )

    source_map = outcome.detail.current_version.source_map
    assert source_map is not None
    assert set(source_map.keys()) == set(outcome.changed_fields) == {"otalgia"}


async def test_k_persisted_document_has_twenty_fields_carried_forward_intact(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )

    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )

    content = outcome.detail.current_version.content
    assert len(content) == 20
    baseline_content = baseline_detail.current_version.content
    for field_name, field_value in content.items():
        if field_name == "otalgia":
            assert field_value["status"] == "informado"
            assert field_value != baseline_content[field_name]
        else:
            assert field_value == baseline_content[field_name]


# ============================================================
# Grupo 3: edit_content sobre una propuesta no debe tocar baseline_*
# (regresión explícita del encargo §13)
# ============================================================


async def test_edit_content_on_proposal_never_touches_baseline_fields(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
):
    current_user = _admin_user(clinic_with_users)
    _, baseline_detail = await _approve_baseline_anamnesis(
        db_session, clinic_with_users, patient.id, current_user
    )
    session, service = await _session_with_transcript(
        db_session,
        clinic_with_users,
        patient.id,
        current_user,
        CORRECTED_VALUE_TRANSCRIPT,
        session_type=SessionType.FOLLOW_UP,
    )
    outcome = await service.propose_anamnesis_update(
        current_user, session.id, f"req-{uuid.uuid4()}"
    )
    original_baseline_artifact_id = outcome.detail.artifact.baseline_artifact_id
    original_baseline_version_id = outcome.detail.artifact.baseline_version_id
    assert original_baseline_artifact_id == baseline_detail.artifact.id

    edited = await service.edit_content(
        current_user,
        outcome.detail.artifact.id,
        f"req-{uuid.uuid4()}",
        content=dict(outcome.detail.current_version.content),
        change_note=None,
    )

    assert edited.artifact.baseline_artifact_id == original_baseline_artifact_id
    assert edited.artifact.baseline_version_id == original_baseline_version_id
