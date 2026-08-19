"""Puerto CalendarIntegration — calendario externo de citas.

PROVISIONAL: firma basada en una investigación ligera de alcance, no en la
API real de ningún proveedor concreto. Solo contrato + mock en el MVP (ver
docs/architecture.md §4) — sin llamada de red real, sin caller desde
ningún otro módulo. Cualquier integración real futura exige su propio
ciclo de análisis de alcance antes de tocarse (ver "Fuera de las fases del
MVP" en docs/development-plan.md).

`CalendarEvent` con campos inspirados en RFC 5545 VEVENT
(`external_event_id` = UID, `starts_at` = DTSTART, `ends_at` = DTEND,
`summary` = SUMMARY); `clinical_session_id` es un enlace interno, no parte
del estándar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True, frozen=True)
class CalendarEvent:
    external_event_id: str
    starts_at: datetime
    ends_at: datetime | None
    summary: str
    clinical_session_id: uuid.UUID | None = None


@dataclass(slots=True, frozen=True)
class CalendarQuery:
    #: Ventana temporal de la consulta; `until` opcional (sin límite superior).
    since: datetime
    until: datetime | None = None


@dataclass(slots=True, frozen=True)
class CalendarAppointmentInput:
    starts_at: datetime
    ends_at: datetime | None
    summary: str
    clinical_session_id: uuid.UUID | None = None


class CalendarIntegration(Protocol):
    async def list_upcoming_sessions(self, input: CalendarQuery) -> list[CalendarEvent]: ...

    async def create_appointment(self, input: CalendarAppointmentInput) -> CalendarEvent: ...
