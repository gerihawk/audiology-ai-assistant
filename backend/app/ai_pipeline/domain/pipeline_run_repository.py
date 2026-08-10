"""Puerto del repositorio de ejecuciones completas del pipeline."""

from __future__ import annotations

import uuid
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
