"""Entidades de dominio del panel de analítica/reporting para la clínica
(Fase 15). Sin dependencia de SQLAlchemy — solo agregaciones de solo
lectura, nunca se persisten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

#: "clinic": vista de ADMIN — agregado de TODA la clínica.
#: "own": vista de AUDIOLOGIST — exclusivamente su propia actividad.
#: Ver `AnalyticsService.get_summary`.
AnalyticsScope = Literal["clinic", "own"]


@dataclass(slots=True, frozen=True)
class PatientStats:
    total: int
    new_in_period: int


@dataclass(slots=True, frozen=True)
class SessionStatusCounts:
    scheduled: int
    in_progress: int
    completed: int
    review_pending: int
    reviewed: int
    cancelled: int


@dataclass(slots=True, frozen=True)
class ArtifactStatusCounts:
    review_pending: int
    approved: int
    rejected: int


@dataclass(slots=True, frozen=True)
class SessionsTrendPoint:
    day: date
    count: int


@dataclass(slots=True, frozen=True)
class ProfessionalActivityEntry:
    professional_id: uuid.UUID
    display_name: str
    sessions_in_period: int


@dataclass(slots=True, frozen=True)
class ClinicAnalyticsSummary:
    """Resultado de `AnalyticsService.get_summary`. `patients` y
    `professional_activity` son `None` en la vista "own" (no tiene
    sentido un recuento de pacientes ni la actividad de otros
    profesionales para un `audiologist`) — nunca `None` en la vista
    "clinic"."""

    scope: AnalyticsScope
    period_days: int
    period_start: datetime
    period_end: datetime
    patients: PatientStats | None
    sessions_total_in_period: int
    sessions_by_status: SessionStatusCounts
    sessions_trend: list[SessionsTrendPoint]
    ai_billable_runs_in_period: int
    ai_artifacts_by_status: ArtifactStatusCounts
    professional_activity: list[ProfessionalActivityEntry] | None
