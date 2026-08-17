"""Tests de `resolve_missing_information_target` y de
`MissingInformationStep.applies_to()`/`patient_context_requirements()` —
Fase 6.4.4, RFC técnico de 6.4 §2-§4/§10-§11. Dominio puro, sin base de
datos."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.patient_context import (
    LoadedPatientContext,
    PatientContextRequirement,
    PreviousAnamnesisRef,
    resolve_missing_information_target,
)
from app.ai_pipeline.domain.pipeline import PipelineExecutionContext
from app.ai_pipeline.domain.steps.anamnesis_step import AnamnesisStep
from app.ai_pipeline.domain.steps.missing_information_step import MissingInformationStep
from app.ai_pipeline.domain.steps.session_notes_step import SessionNotesStep
from app.integrations.domain.missing_information_generator import (
    MissingInformationResult,
    MissingInformationTarget,
)
from app.integrations.domain.session_context import SessionContext
from app.integrations.mocks.mock_anamnesis_generator import MockAnamnesisGenerator
from app.integrations.mocks.mock_cost_estimator import MockCostEstimator
from app.integrations.mocks.mock_missing_information_generator import (
    MockMissingInformationGenerator,
)
from app.integrations.mocks.mock_session_notes_generator import MockSessionNotesGenerator
from app.integrations.mocks.mock_token_counter import MockTokenCounter


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


def _missing_information_step() -> MissingInformationStep:
    return MissingInformationStep(
        MockMissingInformationGenerator(), MockTokenCounter(), MockCostEstimator()
    )


def _anamnesis_step() -> AnamnesisStep:
    return AnamnesisStep(MockAnamnesisGenerator(), MockTokenCounter(), MockCostEstimator())


def _session_notes_step() -> SessionNotesStep:
    return SessionNotesStep(MockSessionNotesGenerator(), MockTokenCounter(), MockCostEstimator())


# --- A. resolve_missing_information_target -----------------------------------


def test_resolve_target_sin_anamnesis_previa_es_anamnesis_fields():
    context = LoadedPatientContext(session_type=None, previous_approved_anamnesis=None)
    assert resolve_missing_information_target(context) == MissingInformationTarget.ANAMNESIS_FIELDS


def test_resolve_target_con_anamnesis_previa_es_session_notes_blocks():
    context = LoadedPatientContext(
        session_type=None, previous_approved_anamnesis=_previous_anamnesis_ref()
    )
    assert (
        resolve_missing_information_target(context) == MissingInformationTarget.SESSION_NOTES_BLOCKS
    )


def test_resolve_target_sin_patient_context_es_none():
    """Caso defensivo (RFC técnico §4): `patient_context` nunca cargado
    nunca inventa un target por defecto."""
    assert resolve_missing_information_target(None) is None


# --- B. invariancia respecto a session_type -----------------------------------


def test_resolve_target_es_invariante_a_session_type_sin_anamnesis_previa():
    targets = {
        resolve_missing_information_target(
            LoadedPatientContext(session_type=session_type, previous_approved_anamnesis=None)
        )
        for session_type in (
            None,
            "initial_assessment",
            "follow_up",
            "hearing_aid_fitting",
        )
    }
    assert targets == {MissingInformationTarget.ANAMNESIS_FIELDS}


def test_resolve_target_es_invariante_a_session_type_con_anamnesis_previa():
    ref = _previous_anamnesis_ref()
    targets = {
        resolve_missing_information_target(
            LoadedPatientContext(session_type=session_type, previous_approved_anamnesis=ref)
        )
        for session_type in (
            None,
            "initial_assessment",
            "follow_up",
            "hearing_aid_fitting",
        )
    }
    assert targets == {MissingInformationTarget.SESSION_NOTES_BLOCKS}


# --- C. MissingInformationStep ------------------------------------------------


def test_declares_previous_approved_anamnesis_requirement():
    assert _missing_information_step().patient_context_requirements() == frozenset(
        {PatientContextRequirement.PREVIOUS_APPROVED_ANAMNESIS}
    )


def test_applies_to_true_sin_anamnesis_previa():
    context = _context(LoadedPatientContext(session_type=None, previous_approved_anamnesis=None))
    assert _missing_information_step().applies_to(context) is True


def test_applies_to_true_con_anamnesis_previa():
    context = _context(
        LoadedPatientContext(
            session_type=None, previous_approved_anamnesis=_previous_anamnesis_ref()
        )
    )
    assert _missing_information_step().applies_to(context) is True


def test_applies_to_false_defensivo_cuando_target_es_none():
    """`patient_context is None` → `resolve_missing_information_target`
    devuelve `None` → `applies_to()` es `False` (rama defensiva de §4:
    "si target=None → SKIPPED_NOT_APPLICABLE", inalcanzable en producción
    bajo el modelo actual, pero manejada explícitamente)."""
    context = _context(None)
    assert _missing_information_step().applies_to(context) is False


# --- D/E parcial: coherencia derivada del MISMO LoadedPatientContext --------


def test_coherencia_sin_anamnesis_previa():
    context = _context(LoadedPatientContext(session_type=None, previous_approved_anamnesis=None))

    assert _anamnesis_step().applies_to(context) is True
    assert _session_notes_step().applies_to(context) is False
    assert (
        resolve_missing_information_target(context.patient_context)
        == MissingInformationTarget.ANAMNESIS_FIELDS
    )


def test_coherencia_con_anamnesis_previa():
    context = _context(
        LoadedPatientContext(
            session_type=None, previous_approved_anamnesis=_previous_anamnesis_ref()
        )
    )

    assert _anamnesis_step().applies_to(context) is False
    assert _session_notes_step().applies_to(context) is True
    assert (
        resolve_missing_information_target(context.patient_context)
        == MissingInformationTarget.SESSION_NOTES_BLOCKS
    )


def test_coherencia_nunca_produce_estados_contradictorios():
    """Para cualquier `LoadedPatientContext`, ANAMNESIS y SESSION_NOTES
    nunca aplican a la vez, y el target de MISSING_INFORMATION siempre
    coincide con el step que sí aplica — los tres derivan del mismo
    objeto, nunca de una lectura independiente."""
    for previous_approved_anamnesis in (None, _previous_anamnesis_ref()):
        context = _context(
            LoadedPatientContext(
                session_type=None, previous_approved_anamnesis=previous_approved_anamnesis
            )
        )
        anamnesis_applies = _anamnesis_step().applies_to(context)
        session_notes_applies = _session_notes_step().applies_to(context)
        target = resolve_missing_information_target(context.patient_context)

        assert anamnesis_applies != session_notes_applies
        if anamnesis_applies:
            assert target == MissingInformationTarget.ANAMNESIS_FIELDS
        else:
            assert target == MissingInformationTarget.SESSION_NOTES_BLOCKS


# --- C (cont.): el step pasa el target correcto al generator, sin I/O ------
#
# Ninguno de estos tests usa `db_session`/`api_client`: `MissingInformationStep.run()`
# solo recibe el `PipelineExecutionContext` ya construido a mano — la
# ausencia de cualquier fixture de base de datos es en sí misma la
# prueba de "no consulta I/O" (RFC técnico §9).


@dataclasses.dataclass(slots=True)
class _SpyMissingInformationGenerator:
    received_target: MissingInformationTarget | None = None

    async def generate(
        self, summary, clinical_flags, *, target: MissingInformationTarget, context
    ) -> MissingInformationResult:
        self.received_target = target
        return MissingInformationResult(items=[])


def _context_with_summary_and_flags(
    patient_context: LoadedPatientContext,
) -> PipelineExecutionContext:
    context = _context(patient_context)
    context.outputs[AIArtifactType.SUMMARY] = {"text": "resumen"}
    context.outputs[AIArtifactType.CLINICAL_FLAGS] = {"flags": []}
    return context


async def test_run_pasa_anamnesis_fields_al_generator_sin_anamnesis_previa():
    spy = _SpyMissingInformationGenerator()
    step = MissingInformationStep(spy, MockTokenCounter(), MockCostEstimator())
    context = _context_with_summary_and_flags(
        LoadedPatientContext(session_type=None, previous_approved_anamnesis=None)
    )

    await step.run(context)

    assert spy.received_target == MissingInformationTarget.ANAMNESIS_FIELDS


async def test_run_pasa_session_notes_blocks_al_generator_con_anamnesis_previa():
    spy = _SpyMissingInformationGenerator()
    step = MissingInformationStep(spy, MockTokenCounter(), MockCostEstimator())
    context = _context_with_summary_and_flags(
        LoadedPatientContext(
            session_type=None, previous_approved_anamnesis=_previous_anamnesis_ref()
        )
    )

    await step.run(context)

    assert spy.received_target == MissingInformationTarget.SESSION_NOTES_BLOCKS
