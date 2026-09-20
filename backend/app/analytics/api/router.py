"""Endpoints /api/v1/analytics (Fase 15 — analítica/reporting para la
clínica). Único endpoint por ahora: `GET /analytics/clinic-summary`,
vista distinta según el rol de `current_user` — ver
`AnalyticsService.get_summary`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.analytics.api.schemas import ClinicAnalyticsSummaryResponse
from app.analytics.service import DEFAULT_PERIOD_DAYS, AnalyticsService
from app.core.current_user import CurrentUser
from app.core.deps import get_analytics_service, get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/clinic-summary", response_model=ClinicAnalyticsSummaryResponse)
async def get_clinic_analytics_summary(
    period_days: int = Query(default=DEFAULT_PERIOD_DAYS, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> ClinicAnalyticsSummaryResponse:
    summary = await service.get_summary(current_user, period_days=period_days)
    return ClinicAnalyticsSummaryResponse.from_domain(summary)
