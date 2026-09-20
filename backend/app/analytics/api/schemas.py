"""Esquemas Pydantic de /api/v1/analytics (Fase 15 — analítica/reporting
para la clínica)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.analytics.domain.entities import (
    AnalyticsScope,
    ArtifactStatusCounts,
    ClinicAnalyticsSummary,
    PatientStats,
    ProfessionalActivityEntry,
    SessionStatusCounts,
    SessionsTrendPoint,
)


class PatientStatsResponse(BaseModel):
    total: int
    new_in_period: int

    @classmethod
    def from_domain(cls, stats: PatientStats) -> PatientStatsResponse:
        return cls(total=stats.total, new_in_period=stats.new_in_period)


class SessionStatusCountsResponse(BaseModel):
    scheduled: int
    in_progress: int
    completed: int
    review_pending: int
    reviewed: int
    cancelled: int

    @classmethod
    def from_domain(cls, counts: SessionStatusCounts) -> SessionStatusCountsResponse:
        return cls(
            scheduled=counts.scheduled,
            in_progress=counts.in_progress,
            completed=counts.completed,
            review_pending=counts.review_pending,
            reviewed=counts.reviewed,
            cancelled=counts.cancelled,
        )


class ArtifactStatusCountsResponse(BaseModel):
    review_pending: int
    approved: int
    rejected: int

    @classmethod
    def from_domain(cls, counts: ArtifactStatusCounts) -> ArtifactStatusCountsResponse:
        return cls(
            review_pending=counts.review_pending,
            approved=counts.approved,
            rejected=counts.rejected,
        )


class SessionsTrendPointResponse(BaseModel):
    day: date
    count: int

    @classmethod
    def from_domain(cls, point: SessionsTrendPoint) -> SessionsTrendPointResponse:
        return cls(day=point.day, count=point.count)


class ProfessionalActivityEntryResponse(BaseModel):
    professional_id: uuid.UUID
    display_name: str
    sessions_in_period: int

    @classmethod
    def from_domain(cls, entry: ProfessionalActivityEntry) -> ProfessionalActivityEntryResponse:
        return cls(
            professional_id=entry.professional_id,
            display_name=entry.display_name,
            sessions_in_period=entry.sessions_in_period,
        )


class ClinicAnalyticsSummaryResponse(BaseModel):
    """Respuesta de `GET /analytics/clinic-summary`. `patients` y
    `professional_activity` son `None` en la vista "own" (`AUDIOLOGIST`) —
    ver `ClinicAnalyticsSummary`."""

    scope: AnalyticsScope
    period_days: int
    period_start: datetime
    period_end: datetime
    patients: PatientStatsResponse | None
    sessions_total_in_period: int
    sessions_by_status: SessionStatusCountsResponse
    sessions_trend: list[SessionsTrendPointResponse]
    ai_billable_runs_in_period: int
    ai_artifacts_by_status: ArtifactStatusCountsResponse
    professional_activity: list[ProfessionalActivityEntryResponse] | None

    @classmethod
    def from_domain(cls, summary: ClinicAnalyticsSummary) -> ClinicAnalyticsSummaryResponse:
        return cls(
            scope=summary.scope,
            period_days=summary.period_days,
            period_start=summary.period_start,
            period_end=summary.period_end,
            patients=(
                PatientStatsResponse.from_domain(summary.patients)
                if summary.patients is not None
                else None
            ),
            sessions_total_in_period=summary.sessions_total_in_period,
            sessions_by_status=SessionStatusCountsResponse.from_domain(summary.sessions_by_status),
            sessions_trend=[
                SessionsTrendPointResponse.from_domain(point) for point in summary.sessions_trend
            ],
            ai_billable_runs_in_period=summary.ai_billable_runs_in_period,
            ai_artifacts_by_status=ArtifactStatusCountsResponse.from_domain(
                summary.ai_artifacts_by_status
            ),
            professional_activity=(
                [
                    ProfessionalActivityEntryResponse.from_domain(entry)
                    for entry in summary.professional_activity
                ]
                if summary.professional_activity is not None
                else None
            ),
        )
