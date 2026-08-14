"""Tests de `SessionNotesStep.applies_to()`/`patient_context_requirements()`
— Fase 6.4.3, RFC técnico de 6.4 §5/§8. Dominio puro, sin base de datos:
espejo exacto e inverso de `test_ai_pipeline_anamnesis_applies_to.py`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.ai_pipeline.domain.patient_context import (
    LoadedPatientContext,
    PatientContextRequirement,
    PreviousAnamnesisRef,
)
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.session_notes_step import SessionNotesStep
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from app.integrations.mocks.mock_session_notes_generator import MockSessionNotesGenerator
from app.integrations.mocks.mock_token_counter import MockTokenCounter


def _step() -> SessionNotesStep:
    return SessionNotesStep(MockSessionNotesGenerator(), MockTokenCounter(), MockCostEstimator())


def _context(patient_context: LoadedPatientContext | None) -> PipelineExecutionContext:
    session_id = uuid.uuid4()
    return PipelineExecutionContext(
        clinical_session_id=session_id,
        session_context=SessionContext(session_id),
        patient_context=patient_context,
    )


def _previous_anamnesis_ref() -> PreviousAnamnesisRef:
    return PreviousAnamnesisRef(
        artifact_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        clinical_session_id=uuid.uuid4(),
        approved_at=datetime.now(UTC),
        content={},
    )


def test_declares_previous_approved_anamnesis_requirement():
    assert _step().patient_context_requirements() == frozenset(
        {PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS}
    )


def test_does_not_apply_when_no_previous_approved_anamnesis():
    context = _context(
        LoadedPatientContext(session_type="initial_assessment", previous_approved_anamnesis=None)
    )
    assert _step().applies_to(context) is False


def test_applies_when_previous_approved_anamnesis_exists():
    context = _context(
        LoadedPatientContext(
            session_type="follow_up", previous_approved_anamnesis=_previous_anamnesis_ref()
        )
    )
    assert _step().applies_to(context) is True


def test_does_not_apply_by_default_when_patient_context_was_never_loaded():
    """`context.patient_context is None` (nunca cargado) se trata como
    "sin confirmación de anamnesis previa": default seguro simétrico e
    inverso al de `AnamnesisStep` — nunca se asume que SESSION_NOTES es
    válido sin esa confirmación."""
    context = _context(None)
    assert _step().applies_to(context) is False


def test_session_type_never_determines_applicability():
    """RFC §2/§4: `session_type` es contexto informativo, nunca un
    interruptor de aplicabilidad."""
    ref = _previous_anamnesis_ref()
    for session_type in (None, "initial_assessment", "hearing_aid_fitting", "other"):
        context = _context(
            LoadedPatientContext(session_type=session_type, previous_approved_anamnesis=ref)
        )
        assert _step().applies_to(context) is True


def test_mutually_exclusive_with_anamnesis_applicability():
    """Espejo exacto: para el mismo `LoadedPatientContext`, ANAMNESIS y
    SESSION_NOTES nunca aplican a la vez ni dejan de aplicar los dos a
    la vez — ver `AnamnesisStep.applies_to()`."""
    from app.ai_pipeline.domain.steps.anamnesis_step import AnamnesisStep
    from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator

    anamnesis_step = AnamnesisStep(
        MockAnamnesisGenerator(), MockTokenCounter(), MockCostEstimator()
    )
    session_notes_step = _step()

    for previous_approved_anamnesis in (None, _previous_anamnesis_ref()):
        context = _context(
            LoadedPatientContext(
                session_type=None, previous_approved_anamnesis=previous_approved_anamnesis
            )
        )
        assert anamnesis_step.applies_to(context) != session_notes_step.applies_to(context)
