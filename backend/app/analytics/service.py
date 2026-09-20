"""AnalyticsService (Fase 15) — panel de analítica/reporting para la
clínica. Candidato "analítica/reporting para la clínica" de la auditoría
posterior a la Fase 14 (docs/development-plan.md).

Vista por rol (decisión de Gerard vía `AskUserQuestion`, "Vista distinta
por rol"): `ADMIN` ve datos agregados de TODA la clínica (incluye
recuento de pacientes y actividad por profesional); `AUDIOLOGIST` ve
EXCLUSIVAMENTE su propia actividad (sus sesiones, sus artefactos de IA,
sus ejecuciones facturables) — nunca datos de otro profesional ni el
agregado completo de la clínica. `VIEWER` no tiene acceso en absoluto
(`authorize_analytics_action`). A diferencia de `authorize_clinical_session_action`
y similares, el alcance no se decide comprobando la propiedad de un
recurso concreto — lo decide este servicio en `get_summary`, según
`current_user.role`, antes de lanzar ninguna consulta.

Servicio de solo lectura, sin efectos secundarios — nunca hace `commit`
ni `flush`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.entities import AIArtifactStatus
from app.ai_pipeline.domain.pipeline_run_repository import AIPipelineRunRepository
from app.ai_pipeline.infrastructure.repository import (
    SqlAlchemyAIArtifactRepository,
    SqlAlchemyAIPipelineRunRepository,
)
from app.analytics.domain.entities import (
    ArtifactStatusCounts,
    ClinicAnalyticsSummary,
    PatientStats,
    ProfessionalActivityEntry,
    SessionStatusCounts,
    SessionsTrendPoint,
)
from app.clinical_sessions.domain.entities import ClinicalSessionStatus
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.core.authorization import AnalyticsAction, authorize_analytics_action
from app.core.current_user import CurrentUser
from app.patients.domain.repository import PatientRepository
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository

#: Ventana por defecto del panel — mismo orden de magnitud que un ciclo
#: de facturación mensual (Fase 13), pero un concepto independiente: este
#: `period_days` es una ventana deslizante desde "ahora", no el periodo
#: de facturación de la clínica (`Clinic.current_period_started_at`).
DEFAULT_PERIOD_DAYS = 30


def _to_session_status_counts(raw: dict[str, int]) -> SessionStatusCounts:
    return SessionStatusCounts(
        scheduled=raw.get(ClinicalSessionStatus.SCHEDULED.value, 0),
        in_progress=raw.get(ClinicalSessionStatus.IN_PROGRESS.value, 0),
        completed=raw.get(ClinicalSessionStatus.COMPLETED.value, 0),
        review_pending=raw.get(ClinicalSessionStatus.REVIEW_PENDING.value, 0),
        reviewed=raw.get(ClinicalSessionStatus.REVIEWED.value, 0),
        cancelled=raw.get(ClinicalSessionStatus.CANCELLED.value, 0),
    )


def _to_artifact_status_counts(raw: dict[str, int]) -> ArtifactStatusCounts:
    return ArtifactStatusCounts(
        review_pending=raw.get(AIArtifactStatus.REVIEW_PENDING.value, 0),
        approved=raw.get(AIArtifactStatus.APPROVED.value, 0),
        rejected=raw.get(AIArtifactStatus.REJECTED.value, 0),
    )


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        patient_repository: PatientRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        artifact_repository: AIArtifactRepository | None = None,
        pipeline_run_repository: AIPipelineRunRepository | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
    ) -> None:
        self._session = session
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._artifacts = artifact_repository or SqlAlchemyAIArtifactRepository()
        self._pipeline_runs = pipeline_run_repository or SqlAlchemyAIPipelineRunRepository()
        self._users = user_repository or SqlAlchemyUserRepository()

    async def get_summary(
        self, current_user: CurrentUser, *, period_days: int = DEFAULT_PERIOD_DAYS
    ) -> ClinicAnalyticsSummary:
        authorize_analytics_action(current_user, AnalyticsAction.READ)

        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(days=period_days)
        is_admin = current_user.role == Role.ADMIN
        # `None` para admin (sin acotar a ningún profesional, agrega toda
        # la clínica); el propio id para audiologist ("own"). `VIEWER` ya
        # fue rechazado por `authorize_analytics_action` — no llega aquí.
        professional_filter: uuid.UUID | None = None if is_admin else current_user.id

        patients: PatientStats | None = None
        if is_admin:
            total = await self._patients.count_for_clinic(self._session, current_user.clinic_id)
            new_in_period = await self._patients.count_for_clinic(
                self._session, current_user.clinic_id, created_since=period_start
            )
            patients = PatientStats(total=total, new_in_period=new_in_period)

        status_counts_raw = await self._clinical_sessions.count_by_status_for_clinic(
            self._session,
            current_user.clinic_id,
            created_since=period_start,
            professional_id=professional_filter,
        )
        sessions_by_status = _to_session_status_counts(status_counts_raw)
        sessions_total = sum(status_counts_raw.values())

        trend_rows = await self._clinical_sessions.count_per_day_for_clinic(
            self._session,
            current_user.clinic_id,
            created_since=period_start,
            professional_id=professional_filter,
        )
        sessions_trend = [SessionsTrendPoint(day=day, count=count) for day, count in trend_rows]

        artifact_counts_raw = await self._artifacts.count_by_status_for_clinic(
            self._session,
            current_user.clinic_id,
            created_since=period_start,
            professional_id=professional_filter,
        )
        ai_artifacts_by_status = _to_artifact_status_counts(artifact_counts_raw)

        billable_runs = await self._pipeline_runs.list_completed_since_for_clinic(
            self._session,
            current_user.clinic_id,
            period_start,
            professional_id=professional_filter,
        )

        professional_activity: list[ProfessionalActivityEntry] | None = None
        if is_admin:
            activity_rows = await self._clinical_sessions.count_by_professional_for_clinic(
                self._session, current_user.clinic_id, created_since=period_start
            )
            professionals = await self._users.list_by_clinic(self._session, current_user.clinic_id)
            names_by_id = {user.id: user.display_name for user in professionals}
            professional_activity = [
                ProfessionalActivityEntry(
                    professional_id=professional_id,
                    # No debería faltar (todo `professional_id` de una
                    # sesión referencia un `User` de la misma clínica),
                    # pero un usuario borrado físicamente en algún flujo
                    # de purga no debe romper el panel.
                    display_name=names_by_id.get(professional_id, "Profesional eliminado"),
                    sessions_in_period=count,
                )
                for professional_id, count in activity_rows
            ]

        return ClinicAnalyticsSummary(
            scope="clinic" if is_admin else "own",
            period_days=period_days,
            period_start=period_start,
            period_end=period_end,
            patients=patients,
            sessions_total_in_period=sessions_total,
            sessions_by_status=sessions_by_status,
            sessions_trend=sessions_trend,
            ai_billable_runs_in_period=len(billable_runs),
            ai_artifacts_by_status=ai_artifacts_by_status,
            professional_activity=professional_activity,
        )
