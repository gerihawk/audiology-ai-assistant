"""Puerto del repositorio de ejecuciones completas del pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIPipelineRun


class AIPipelineRunRepository(Protocol):
    async def add(self, session: AsyncSession, run: AIPipelineRun) -> AIPipelineRun: ...

    async def update_fields(
        self, session: AsyncSession, run_id: uuid.UUID, values: dict[str, Any]
    ) -> AIPipelineRun | None: ...

    async def get_active_for_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> AIPipelineRun | None:
        """Ejecución `queued`/`processing` en curso para la sesión, si
        existe — usada para rechazar un segundo disparo concurrente."""
        ...

    async def delete_for_sessions(
        self, session: AsyncSession, clinical_session_ids: list[uuid.UUID]
    ) -> int:
        """Borrado físico definitivo — usado EXCLUSIVAMENTE por
        `RetentionCleanupService.purge_patient_clinical_data()`. Debe
        llamarse después de `AIGenerationRunRepository.
        delete_for_sessions()` (que ya borró las filas que referencian
        `ai_pipeline_run_id`). Devuelve el nº de filas eliminadas."""
        ...

    async def list_completed_since_for_clinic(
        self, session: AsyncSession, clinic_id: uuid.UUID, since: datetime
    ) -> list[AIPipelineRun]:
        """Fase 13, hito 13.2 — ejecuciones del pipeline de la clínica dada,
        terminadas (`completed_at` no nulo, éxito o fallo — un intento
        fallido igual consumió recursos) desde `since` (inicio del periodo
        de facturación actual), ordenadas por `started_at`: el mismo orden
        en que `AIPipelineService.run_pipeline` fue incrementando
        `Clinic.sessions_used_this_period`, para que
        `BillingService.report_overage_usage` pueda recortar exactamente
        las que superan el tope incluido del nivel. No distingue
        `run-pipeline` de `run-mock-pipeline` a nivel de esta consulta —
        `AIPipelineService` es quien garantiza que el mock nunca incrementa
        el contador ni, por tanto, aparece contado como overage."""
        ...
