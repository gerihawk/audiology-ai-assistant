"""Tests de `AnamnesisStep.applies_to()`/`patient_context_requirements()`
— Fase 6.4.2, RFC técnico §5. Dominio puro, sin base de datos: construye
`PipelineExecutionContext`/`LoadedPatientContext` directamente, sin pasar
por `AIPipelineService` ni por el orquestador."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.ai_pipeline.domain.patient_context import (
    LoadedPatientContext,
    PatientContextRequirement,
    PreviousAnamnesisRef,
)
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.anamnesis_step import AnamnesisStep
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from app.integrations.mocks.mock_token_counter import MockTokenCounter


def _step() -> AnamnesisStep:
    return AnamnesisStep(MockAnamnesisGenerator(), MockTokenCounter(), MockCostEstimator())


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


def test_applies_when_no_previous_approved_anamnesis():
    context = _context(
        LoadedPatientContext(session_type="initial_assessment", previous_approved_anamnesis=None)
    )
    assert _step().applies_to(context) is True


def test_does_not_apply_when_previous_approved_anamnesis_exists():
    context = _context(
        LoadedPatientContext(
            session_type="follow_up", previous_approved_anamnesis=_previous_anamnesis_ref()
        )
    )
    assert _step().applies_to(context) is False


def test_applies_by_default_when_patient_context_was_never_loaded():
    """`context.patient_context is None` (nunca cargado — p. ej. un
    `PipelineExecutionContext` construido a mano) se trata como "sin
    anamnesis previa conocida": mismo comportamiento por defecto que
    tenía este step antes de 6.4.2."""
    context = _context(None)
    assert _step().applies_to(context) is True


def test_session_type_never_determines_applicability():
    """RFC §2/§4: `session_type` es contexto informativo, nunca un
    interruptor de aplicabilidad — el mismo `previous_approved_anamnesis`
    produce el mismo resultado sin importar el `session_type`, incluido
    `None` (legacy)."""
    ref = _previous_anamnesis_ref()
    for session_type in (None, "initial_assessment", "hearing_aid_fitting", "other"):
        context = _context(
            LoadedPatientContext(session_type=session_type, previous_approved_anamnesis=ref)
        )
        assert _step().applies_to(context) is False
