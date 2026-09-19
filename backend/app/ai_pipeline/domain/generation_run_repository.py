"""Puerto del repositorio de ejecuciones de un paso del pipeline
(auditoría técnica: proveedor, modelo, latencia, tokens, coste)."""

from __future__ import annotations

import uuid
from decimal import Decimal
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

    async def sum_estimated_cost_for_session(
        self, session: AsyncSession, clinical_session_id: uuid.UUID
    ) -> Decimal:
        """Coste real/estimado ya acumulado para esta sesión clínica, a
        través de todas sus `AIGenerationRun` previas (cualquier
        `AIPipelineRun`) — base de `SessionCostBudget.accumulated_usd` al
        arrancar una nueva ejecución (ver docs/fase-6-rfc.md §6.3)."""
        ...

    async def sum_estimated_cost_for_pipeline_runs(
        self, session: AsyncSession, ai_pipeline_run_ids: list[uuid.UUID]
    ) -> Decimal:
        """Fase 13, hito 13.2 — coste agregado de las `AIGenerationRun` de
        los `AIPipelineRun` dados (típicamente los que superan el tope
        incluido del nivel, ver
        `AIPipelineRunRepository.list_completed_since_for_clinic`), base de
        `BillingService.report_overage_usage`. Lista vacía devuelve 0 sin
        consultar la base de datos."""
        ...

    async def delete_for_sessions(
        self, session: AsyncSession, clinical_session_ids: list[uuid.UUID]
    ) -> int:
        """Borrado físico definitivo — usado EXCLUSIVAMENTE por
        `RetentionCleanupService.purge_patient_clinical_data()`. Debe
        llamarse después de `AIArtifactRepository.
        prepare_purge_for_sessions()` (que ya borró las
        `ai_artifact_versions` que referenciaban estas ejecuciones vía
        `generation_run_id`) y antes de `AIArtifactRepository.
        finish_purge()` (que exige que ya no exista ningún
        `ai_generation_runs.ai_artifact_id` apuntando a esos
        artefactos). Devuelve el nº de filas eliminadas."""
        ...
