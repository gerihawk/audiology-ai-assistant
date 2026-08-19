"""MockCalendarIntegration: determinista, sin I/O de red.

Misma entrada -> misma salida (ver docs/architecture.md §4) — mismo
criterio de test que el resto de `Mock*` del proyecto (Fase 4.4). Sin
caller todavía: contrato + mock probado, ver docs/development-plan.md
Fase 7.3.
"""

from __future__ import annotations

import hashlib

from app.integrations.domain.calendar_integration import (
    CalendarAppointmentInput,
    CalendarEvent,
    CalendarQuery,
)


def _fake_external_event_id(seed: str) -> str:
    return f"cal-{hashlib.sha256(seed.encode()).hexdigest()[:12]}"


class MockCalendarIntegration:
    async def list_upcoming_sessions(self, input: CalendarQuery) -> list[CalendarEvent]:
        # Fixture vacía y determinista: sin calendario real de por medio,
        # no hay eventos "próximos" que inventar (ver docs/architecture.md §4).
        return []

    async def create_appointment(self, input: CalendarAppointmentInput) -> CalendarEvent:
        seed = f"{input.starts_at.isoformat()}|{input.summary}"
        return CalendarEvent(
            external_event_id=_fake_external_event_id(seed),
            starts_at=input.starts_at,
            ends_at=input.ends_at,
            summary=input.summary,
            clinical_session_id=input.clinical_session_id,
        )
