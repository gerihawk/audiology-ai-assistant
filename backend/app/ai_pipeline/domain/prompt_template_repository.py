"""Puerto del repositorio de plantillas de prompt.

Fase 4.1: solo infraestructura (tabla + repositorio). Ningún paso del
pipeline la usa todavía — ver docs/ai-pipeline-architecture.md §7.4 y
docs/development-plan.md Fase 4.7 (gestión de prompts, fuera de esta
ronda)."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import PromptTemplate


class PromptTemplateRepository(Protocol):
    async def get_active_by_name(
        self, session: AsyncSession, name: str
    ) -> PromptTemplate | None: ...

    async def add(self, session: AsyncSession, template: PromptTemplate) -> PromptTemplate: ...

    async def get_by_id(
        self, session: AsyncSession, template_id: uuid.UUID
    ) -> PromptTemplate | None: ...
