"""MockPatientRecordIntegration / MockCalendarIntegration — Fase 7.3
(docs/development-plan.md): determinismo (misma entrada -> misma salida),
sin I/O de red, y sin ningún caller real desde el resto del backend
(contrato + mock probado, ver docs/architecture.md §4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.domain.calendar_integration import CalendarAppointmentInput, CalendarQuery
from app.integrations.domain.patient_record_integration import PatientRecordSyncInput
from app.integrations.mocks.mock_calendar_integration import MockCalendarIntegration
from app.integrations.mocks.mock_patient_record_integration import MockPatientRecordIntegration

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
_FORBIDDEN_SYMBOLS = (
    "MockPatientRecordIntegration",
    "MockCalendarIntegration",
    "PatientRecordIntegration",
    "CalendarIntegration",
)


# --- Determinismo, sin I/O de red -----------------------------------------


async def test_mock_patient_record_sync_is_deterministic():
    mock = MockPatientRecordIntegration()
    input = PatientRecordSyncInput(
        patient_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        first_name="Paciente",
        last_name="Ficticio",
        date_of_birth=datetime(1970, 1, 1, tzinfo=UTC).date(),
    )

    first = await mock.sync_patient(input)
    second = await mock.sync_patient(input)

    assert first == second
    assert first.status == "synced"


async def test_mock_patient_record_sync_reuses_existing_reference():
    mock = MockPatientRecordIntegration()
    input = PatientRecordSyncInput(
        patient_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        first_name="Paciente",
        last_name="Ficticio",
        date_of_birth=datetime(1970, 1, 1, tzinfo=UTC).date(),
        external_reference_id="noah-existing",
    )

    result = await mock.sync_patient(input)

    assert result.external_reference_id == "noah-existing"


async def test_mock_patient_record_fetch_is_deterministic():
    mock = MockPatientRecordIntegration()

    first = await mock.fetch_patient("noah-abc123")
    second = await mock.fetch_patient("noah-abc123")

    assert first == second
    assert first is not None
    assert first.external_reference_id == "noah-abc123"


async def test_mock_patient_record_fetch_unknown_reference_returns_none():
    mock = MockPatientRecordIntegration()

    result = await mock.fetch_patient("unrelated-id")

    assert result is None


async def test_mock_calendar_create_appointment_is_deterministic():
    mock = MockCalendarIntegration()
    input = CalendarAppointmentInput(
        starts_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
        summary="Consulta ficticia",
    )

    first = await mock.create_appointment(input)
    second = await mock.create_appointment(input)

    assert first == second


async def test_mock_calendar_list_upcoming_sessions_is_empty_and_deterministic():
    mock = MockCalendarIntegration()
    query = CalendarQuery(since=datetime(2026, 1, 1, tzinfo=UTC))

    first = await mock.list_upcoming_sessions(query)
    second = await mock.list_upcoming_sessions(query)

    assert first == second == []


# --- Sin caller real fuera de integrations/ --------------------------------


def test_patient_record_and_calendar_integrations_have_no_real_caller():
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "integrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for symbol in _FORBIDDEN_SYMBOLS:
            if symbol in text:
                offenders.append(f"{path.relative_to(APP_ROOT)}: {symbol}")
    assert offenders == []
