"""Tests de dominio puro de los value objects de contexto de la Fase
6.4.1 — sin base de datos. Verifica en particular que ninguno de estos
tipos puede transportar un repositorio o una `AsyncSession` (RFC técnico
de 6.4.1, §3): un campo de ese tipo aquí haría fallar estos tests, no
solo una revisión manual."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.patient_context import LoadedPatientContext, PreviousAnamnesisRef
from app.integrations.domain.session_context import SessionContext

_ALLOWED_FIELD_TYPES = (uuid.UUID, datetime, dict, str, type(None))


class TestSessionContextSessionType:
    def test_session_type_round_trips(self):
        session_id = uuid.uuid4()
        context = SessionContext(clinical_session_id=session_id, session_type="initial_assessment")
        assert context.session_type == "initial_assessment"

    def test_session_type_defaults_to_none_for_backward_compatible_single_arg_construction(self):
        """Construcción posicional de un único argumento — la que ya usan
        callers/tests anteriores a 6.4.1 — debe seguir funcionando sin
        modificarse."""
        session_id = uuid.uuid4()
        context = SessionContext(session_id)
        assert context.clinical_session_id == session_id
        assert context.session_type is None

    def test_none_session_type_is_preserved_explicitly(self):
        """Caso legacy (docs/fase-6-rfc.md §3.3): `None` es un valor
        válido y debe distinguirse de "no se pasó nada"."""
        context = SessionContext(clinical_session_id=uuid.uuid4(), session_type=None)
        assert context.session_type is None


class TestLoadedPatientContextShape:
    def test_constructs_with_no_previous_anamnesis(self):
        context = LoadedPatientContext(session_type=None, previous_approved_anamnesis=None)
        assert context.previous_approved_anamnesis is None

    def test_constructs_with_previous_anamnesis_ref(self):
        ref = PreviousAnamnesisRef(
            artifact_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            clinical_session_id=uuid.uuid4(),
            approved_at=datetime.now(UTC),
            content={"tinnitus": {"value": "...", "status": "informado"}},
        )
        context = LoadedPatientContext(session_type="follow_up", previous_approved_anamnesis=ref)
        assert context.previous_approved_anamnesis is ref

    def test_is_frozen(self):
        context = LoadedPatientContext(session_type=None, previous_approved_anamnesis=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            context.session_type = "other"  # type: ignore[misc]

    def test_exposes_only_the_expected_fields_never_a_repository_or_session(self):
        field_names = {f.name for f in dataclasses.fields(LoadedPatientContext)}
        assert field_names == {"session_type", "previous_approved_anamnesis"}


class TestPreviousAnamnesisRefShape:
    def test_transports_baseline_artifact_and_version_identity(self):
        """Hito 6.5.1: identidad exacta del baseline, necesaria para
        optimistic concurrency en la aprobación de una propuesta de
        actualización — ver auditoría de 6.5, Decisión 2."""
        artifact_id = uuid.uuid4()
        version_id = uuid.uuid4()
        ref = PreviousAnamnesisRef(
            artifact_id=artifact_id,
            version_id=version_id,
            clinical_session_id=uuid.uuid4(),
            approved_at=datetime.now(UTC),
            content={},
        )
        assert ref.artifact_id == artifact_id
        assert ref.version_id == version_id

    def test_is_frozen(self):
        ref = PreviousAnamnesisRef(
            artifact_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            clinical_session_id=uuid.uuid4(),
            approved_at=datetime.now(UTC),
            content={},
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.content = {"x": "y"}  # type: ignore[misc]

    def test_exposes_only_minimal_fields(self):
        field_names = {f.name for f in dataclasses.fields(PreviousAnamnesisRef)}
        assert field_names == {
            "artifact_id",
            "version_id",
            "clinical_session_id",
            "approved_at",
            "content",
        }

    def test_field_types_are_plain_values_never_session_or_repository(self):
        for f in dataclasses.fields(PreviousAnamnesisRef):
            # `dict[str, Any]`/`uuid.UUID`/`datetime` — nunca AsyncSession
            # ni un tipo de repositorio del propio backend.
            assert "Session" not in str(f.type)
            assert "Repository" not in str(f.type)
