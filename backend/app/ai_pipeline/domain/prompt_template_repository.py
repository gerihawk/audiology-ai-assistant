"""Puerto del repositorio de plantillas de prompt.

Fase 4.1: tabla + repositorio mínimo (`get_active_by_name`/`add`/`get_by_id`).
Fase 6.0.5 (docs/development-plan.md): añade `get_active()` por
`artifact_type`/`language` — selección real de plantilla, todavía sin que
ningún paso del pipeline la use (eso llega en la Fase 6.1, ver
docs/fase-6-rfc.md §10). `get_active_by_name` se conserva sin cambios para
compatibilidad absoluta con el código existente."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate


class PromptTemplateRepository(Protocol):
    async def get_active_by_name(
        self, session: AsyncSession, name: str
    ) -> PromptTemplate | None: ...

    async def get_active(
        self, session: AsyncSession, artifact_type: AIArtifactType, language: str
    ) -> PromptTemplate | None: ...

    async def add(self, session: AsyncSession, template: PromptTemplate) -> PromptTemplate: ...

    async def get_by_id(
        self, session: AsyncSession, template_id: uuid.UUID
    ) -> PromptTemplate | None: ...

    async def deactivate(self, session: AsyncSession, template_id: uuid.UUID) -> None:
        """Publicar una versión nueva es `add()` con `is_active=True` tras
        desactivar la anterior con este método — dos pasos explícitos del
        llamador, nunca automático dentro de `add()` (ver
        docs/ai-pipeline-architecture.md §7.4: append-only, cada fila se
        conserva íntegra)."""
        ...


class PromptTemplateNotFoundError(Exception):
    """No existe una plantilla activa para `(artifact_type, language)`.

    Política de fallback — documentada, no automática: nunca se sustituye
    en silencio por otro idioma, otra versión o una plantilla por
    defecto. Un llamador que necesite un idioma de respaldo debe
    reintentar explícitamente con ese idioma; nunca ocurre de forma
    implícita — "nunca sustituciones silenciosas"
    (docs/clinical-safety.md, docs/development-plan.md Fase 6.0.5)."""

    def __init__(self, artifact_type: AIArtifactType, language: str) -> None:
        super().__init__(
            "No existe una plantilla de prompt activa para "
            f"artifact_type='{artifact_type.value}' language='{language}'."
        )
        self.artifact_type = artifact_type
        self.language = language


async def require_active_template(
    session: AsyncSession,
    repository: PromptTemplateRepository,
    artifact_type: AIArtifactType,
    language: str,
) -> PromptTemplate:
    """Carga la plantilla activa o falla explícitamente — ver
    `PromptTemplateNotFoundError` para la política de fallback."""
    template = await repository.get_active(session, artifact_type, language)
    if template is None:
        raise PromptTemplateNotFoundError(artifact_type, language)
    return template
