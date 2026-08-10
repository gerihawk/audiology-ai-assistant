"""Puerto del repositorio de ejecuciones de un paso del pipeline
(auditoría técnica: proveedor, modelo, latencia, tokens, coste)."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIGenerationRun


class AIGenerationRunRepository(Protocol):
    async def add(self, session: AsyncSession, run: AIGenerationRun) -> AIGenerationRun: ...

    async def get_by_id(
        self, session: AsyncSession, run_id: uuid.UUID
    ) -> AIGenerationRun | None: ...

    async def list_by_pipeline_run(
        self, session: AsyncSession, ai_pipeline_run_id: uuid.UUID
    ) -> list[AIGenerationRun]: ...
