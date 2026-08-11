"""Puerto del repositorio de artefactos de IA y sus versiones.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifact, AIArtifactType, AIArtifactVersion


class AIArtifactRepository(Protocol):
    async def get_by_id(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        artifact_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> AIArtifact | None:
        """Excluye por defecto los artefactos con soft-delete
        (`deleted_at IS NOT NULL`) — ver docs/fase-6-rfc.md §7.3.
        `include_deleted=True` solo lo usa el propio flujo de borrado,
        para su comprobación de idempotencia."""
        ...

    async def get_by_session_and_type(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        clinical_session_id: uuid.UUID,
        artifact_type: AIArtifactType,
    ) -> AIArtifact | None:
        """Excluye por defecto los artefactos con soft-delete."""
        ...

    async def list_by_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> list[AIArtifact]:
        """Excluye por defecto los artefactos con soft-delete."""
        ...

    async def latest_version_number(self, session: AsyncSession, ai_artifact_id: uuid.UUID) -> int:
        """Devuelve el `version_number` más alto ya persistido, o 0 si no
        existe ninguna versión todavía (permite calcular `+ 1` sin
        distinguir el caso de artefacto nuevo)."""
        ...

    async def insert_new(self, session: AsyncSession, artifact: AIArtifact) -> AIArtifact:
        """Inserta un `AIArtifact` nuevo con `current_version_id = None` —
        deliberadamente sin versión todavía, para poder insertar después la
        `AIArtifactVersion` (que exige `ai_artifact_id` ya existente) y el
        `AIGenerationRun` que la produjo, y solo entonces actualizar
        `current_version_id` vía `update_disposition`. Resuelve el orden de
        inserción de la dependencia circular entre ambas tablas — ver
        docs/data-model.md §10."""
        ...

    async def insert_version(
        self, session: AsyncSession, version: AIArtifactVersion
    ) -> AIArtifactVersion:
        """Inserta una `AIArtifactVersion` nueva. `version.ai_artifact_id`
        debe referenciar un `AIArtifact` ya existente."""
        ...

    async def get_version_by_id(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> AIArtifactVersion | None: ...

    async def list_versions(
        self, session: AsyncSession, ai_artifact_id: uuid.UUID
    ) -> list[AIArtifactVersion]:
        """Historial completo, más reciente primero. Solo lectura — nunca
        se edita ni se borra una versión existente."""
        ...

    async def update_disposition(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        artifact_id: uuid.UUID,
        values: dict[str, Any],
    ) -> AIArtifact | None: ...
