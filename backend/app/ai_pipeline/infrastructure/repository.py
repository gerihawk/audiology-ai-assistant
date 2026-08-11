"""Implementaciones SQLAlchemy de los repositorios del AI Pipeline."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
    AIGenerationRun,
    AIGenerationRunStatus,
    AIPipelineRun,
    AIPipelineRunStatus,
    PromptTemplate,
)
from app.ai_pipeline.infrastructure.orm import (
    AIArtifactORM,
    AIArtifactVersionORM,
    AIGenerationRunORM,
    AIPipelineRunORM,
    PromptTemplateORM,
)


def _artifact_to_domain(row: AIArtifactORM) -> AIArtifact:
    return AIArtifact(
        id=row.id,
        clinical_session_id=row.clinical_session_id,
        artifact_type=AIArtifactType(row.artifact_type),
        status=AIArtifactStatus(row.status),
        current_version_id=row.current_version_id,
        confidence=row.confidence,
        schema_version=row.schema_version,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        rejected_by=row.rejected_by,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        deleted_by=row.deleted_by,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version_to_domain(row: AIArtifactVersionORM) -> AIArtifactVersion:
    return AIArtifactVersion(
        id=row.id,
        ai_artifact_id=row.ai_artifact_id,
        version_number=row.version_number,
        content=row.content,
        confidence=row.confidence,
        source_map=row.source_map,
        source=AIArtifactVersionSource(row.source),
        generation_run_id=row.generation_run_id,
        created_by=row.created_by,
        change_note=row.change_note,
        created_at=row.created_at,
    )


def _generation_run_to_domain(row: AIGenerationRunORM) -> AIGenerationRun:
    return AIGenerationRun(
        id=row.id,
        ai_pipeline_run_id=row.ai_pipeline_run_id,
        clinical_session_id=row.clinical_session_id,
        artifact_type=AIArtifactType(row.artifact_type),
        ai_artifact_id=row.ai_artifact_id,
        resulting_version_number=row.resulting_version_number,
        status=AIGenerationRunStatus(row.status),
        provider_name=row.provider_name,
        model_name=row.model_name,
        prompt_template_id=row.prompt_template_id,
        prompt_template_version=row.prompt_template_version,
        input_token_count=row.input_token_count,
        output_token_count=row.output_token_count,
        estimated_cost_usd=row.estimated_cost_usd,
        latency_ms=row.latency_ms,
        execution_time_ms=row.execution_time_ms,
        rendered_system_prompt=row.rendered_system_prompt,
        rendered_user_prompt=row.rendered_user_prompt,
        raw_response=row.raw_response,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_reason=row.failure_reason,
        request_id=row.request_id,
    )


def _pipeline_run_to_domain(row: AIPipelineRunORM) -> AIPipelineRun:
    return AIPipelineRun(
        id=row.id,
        clinical_session_id=row.clinical_session_id,
        triggered_by=row.triggered_by,
        status=AIPipelineRunStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        request_id=row.request_id,
    )


def _prompt_template_to_domain(row: PromptTemplateORM) -> PromptTemplate:
    return PromptTemplate(
        id=row.id,
        name=row.name,
        version=row.version,
        description=row.description,
        system_prompt=row.system_prompt,
        user_prompt_template=row.user_prompt_template,
        variables_schema=row.variables_schema,
        is_active=row.is_active,
        created_by=row.created_by,
        change_note=row.change_note,
        created_at=row.created_at,
        artifact_type=AIArtifactType(row.artifact_type),
        language=row.language,
    )


class SqlAlchemyAIArtifactRepository:
    async def get_by_id(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        artifact_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> AIArtifact | None:
        from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM

        query = (
            select(AIArtifactORM)
            .join(ClinicalSessionORM, AIArtifactORM.clinical_session_id == ClinicalSessionORM.id)
            .where(AIArtifactORM.id == artifact_id, ClinicalSessionORM.clinic_id == clinic_id)
        )
        if not include_deleted:
            query = query.where(AIArtifactORM.deleted_at.is_(None))
        result = await session.execute(query)
        row = result.scalar_one_or_none()
        return _artifact_to_domain(row) if row is not None else None

    async def get_by_session_and_type(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        clinical_session_id: uuid.UUID,
        artifact_type: AIArtifactType,
    ) -> AIArtifact | None:
        from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM

        result = await session.execute(
            select(AIArtifactORM)
            .join(ClinicalSessionORM, AIArtifactORM.clinical_session_id == ClinicalSessionORM.id)
            .where(
                AIArtifactORM.clinical_session_id == clinical_session_id,
                AIArtifactORM.artifact_type == artifact_type.value,
                ClinicalSessionORM.clinic_id == clinic_id,
                AIArtifactORM.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return _artifact_to_domain(row) if row is not None else None

    async def list_by_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> list[AIArtifact]:
        from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM

        result = await session.execute(
            select(AIArtifactORM)
            .join(ClinicalSessionORM, AIArtifactORM.clinical_session_id == ClinicalSessionORM.id)
            .where(
                AIArtifactORM.clinical_session_id == clinical_session_id,
                ClinicalSessionORM.clinic_id == clinic_id,
                AIArtifactORM.deleted_at.is_(None),
            )
            .order_by(AIArtifactORM.artifact_type.asc())
        )
        rows = result.scalars().all()
        return [_artifact_to_domain(row) for row in rows]

    async def latest_version_number(self, session: AsyncSession, ai_artifact_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.max(AIArtifactVersionORM.version_number)).where(
                AIArtifactVersionORM.ai_artifact_id == ai_artifact_id
            )
        )
        return result.scalar_one() or 0

    async def insert_new(self, session: AsyncSession, artifact: AIArtifact) -> AIArtifact:
        row = AIArtifactORM(
            id=artifact.id,
            clinical_session_id=artifact.clinical_session_id,
            artifact_type=artifact.artifact_type.value,
            status=artifact.status.value,
            current_version_id=None,
            confidence=None,
            schema_version=artifact.schema_version,
        )
        session.add(row)
        await session.flush()
        return _artifact_to_domain(row)

    async def insert_version(
        self, session: AsyncSession, version: AIArtifactVersion
    ) -> AIArtifactVersion:
        row = AIArtifactVersionORM(
            id=version.id,
            ai_artifact_id=version.ai_artifact_id,
            version_number=version.version_number,
            content=version.content,
            confidence=version.confidence,
            source_map=version.source_map,
            source=version.source.value,
            generation_run_id=version.generation_run_id,
            created_by=version.created_by,
            change_note=version.change_note,
        )
        session.add(row)
        await session.flush()
        return _version_to_domain(row)

    async def get_version_by_id(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> AIArtifactVersion | None:
        result = await session.execute(
            select(AIArtifactVersionORM).where(AIArtifactVersionORM.id == version_id)
        )
        row = result.scalar_one_or_none()
        return _version_to_domain(row) if row is not None else None

    async def list_versions(
        self, session: AsyncSession, ai_artifact_id: uuid.UUID
    ) -> list[AIArtifactVersion]:
        result = await session.execute(
            select(AIArtifactVersionORM)
            .where(AIArtifactVersionORM.ai_artifact_id == ai_artifact_id)
            .order_by(AIArtifactVersionORM.version_number.desc())
        )
        return [_version_to_domain(row) for row in result.scalars().all()]

    async def update_disposition(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        artifact_id: uuid.UUID,
        values: dict[str, Any],
    ) -> AIArtifact | None:
        from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM

        result = await session.execute(
            select(AIArtifactORM)
            .join(ClinicalSessionORM, AIArtifactORM.clinical_session_id == ClinicalSessionORM.id)
            .where(AIArtifactORM.id == artifact_id, ClinicalSessionORM.clinic_id == clinic_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if isinstance(value, AIArtifactStatus):
                value = value.value
            setattr(row, key, value)
        await session.flush()
        return _artifact_to_domain(row)


class SqlAlchemyAIGenerationRunRepository:
    async def add(self, session: AsyncSession, run: AIGenerationRun) -> AIGenerationRun:
        row = AIGenerationRunORM(
            id=run.id,
            ai_pipeline_run_id=run.ai_pipeline_run_id,
            clinical_session_id=run.clinical_session_id,
            artifact_type=run.artifact_type.value,
            ai_artifact_id=run.ai_artifact_id,
            resulting_version_number=run.resulting_version_number,
            status=run.status.value,
            provider_name=run.provider_name,
            model_name=run.model_name,
            prompt_template_id=run.prompt_template_id,
            prompt_template_version=run.prompt_template_version,
            input_token_count=run.input_token_count,
            output_token_count=run.output_token_count,
            estimated_cost_usd=run.estimated_cost_usd,
            latency_ms=run.latency_ms,
            execution_time_ms=run.execution_time_ms,
            rendered_system_prompt=run.rendered_system_prompt,
            rendered_user_prompt=run.rendered_user_prompt,
            raw_response=run.raw_response,
            started_at=run.started_at,
            completed_at=run.completed_at,
            failure_reason=run.failure_reason,
            request_id=run.request_id,
        )
        session.add(row)
        await session.flush()
        return _generation_run_to_domain(row)

    async def get_by_id(self, session: AsyncSession, run_id: uuid.UUID) -> AIGenerationRun | None:
        result = await session.execute(
            select(AIGenerationRunORM).where(AIGenerationRunORM.id == run_id)
        )
        row = result.scalar_one_or_none()
        return _generation_run_to_domain(row) if row is not None else None

    async def list_by_pipeline_run(
        self, session: AsyncSession, ai_pipeline_run_id: uuid.UUID
    ) -> list[AIGenerationRun]:
        result = await session.execute(
            select(AIGenerationRunORM).where(
                AIGenerationRunORM.ai_pipeline_run_id == ai_pipeline_run_id
            )
        )
        return [_generation_run_to_domain(row) for row in result.scalars().all()]

    async def sum_estimated_cost_for_session(
        self, session: AsyncSession, clinical_session_id: uuid.UUID
    ) -> Decimal:
        result = await session.execute(
            select(
                func.coalesce(func.sum(AIGenerationRunORM.estimated_cost_usd), Decimal("0"))
            ).where(AIGenerationRunORM.clinical_session_id == clinical_session_id)
        )
        return result.scalar_one()


class SqlAlchemyAIPipelineRunRepository:
    async def add(self, session: AsyncSession, run: AIPipelineRun) -> AIPipelineRun:
        row = AIPipelineRunORM(
            id=run.id,
            clinical_session_id=run.clinical_session_id,
            triggered_by=run.triggered_by,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            request_id=run.request_id,
        )
        session.add(row)
        await session.flush()
        return _pipeline_run_to_domain(row)

    async def update_fields(
        self, session: AsyncSession, run_id: uuid.UUID, values: dict[str, Any]
    ) -> AIPipelineRun | None:
        result = await session.execute(
            select(AIPipelineRunORM).where(AIPipelineRunORM.id == run_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if isinstance(value, AIPipelineRunStatus):
                value = value.value
            setattr(row, key, value)
        await session.flush()
        return _pipeline_run_to_domain(row)

    async def get_active_for_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> AIPipelineRun | None:
        from app.clinical_sessions.infrastructure.orm import ClinicalSessionORM

        result = await session.execute(
            select(AIPipelineRunORM)
            .join(ClinicalSessionORM, AIPipelineRunORM.clinical_session_id == ClinicalSessionORM.id)
            .where(
                AIPipelineRunORM.clinical_session_id == clinical_session_id,
                ClinicalSessionORM.clinic_id == clinic_id,
                AIPipelineRunORM.status.in_(
                    [AIPipelineRunStatus.QUEUED.value, AIPipelineRunStatus.PROCESSING.value]
                ),
            )
        )
        row = result.scalar_one_or_none()
        return _pipeline_run_to_domain(row) if row is not None else None


class SqlAlchemyPromptTemplateRepository:
    async def get_active_by_name(self, session: AsyncSession, name: str) -> PromptTemplate | None:
        result = await session.execute(
            select(PromptTemplateORM).where(
                PromptTemplateORM.name == name, PromptTemplateORM.is_active.is_(True)
            )
        )
        row = result.scalar_one_or_none()
        return _prompt_template_to_domain(row) if row is not None else None

    async def get_active(
        self, session: AsyncSession, artifact_type: AIArtifactType, language: str
    ) -> PromptTemplate | None:
        result = await session.execute(
            select(PromptTemplateORM).where(
                PromptTemplateORM.artifact_type == artifact_type.value,
                PromptTemplateORM.language == language,
                PromptTemplateORM.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return _prompt_template_to_domain(row) if row is not None else None

    async def add(self, session: AsyncSession, template: PromptTemplate) -> PromptTemplate:
        row = PromptTemplateORM(
            id=template.id,
            name=template.name,
            version=template.version,
            description=template.description,
            system_prompt=template.system_prompt,
            user_prompt_template=template.user_prompt_template,
            variables_schema=template.variables_schema,
            is_active=template.is_active,
            created_by=template.created_by,
            change_note=template.change_note,
            artifact_type=template.artifact_type.value,
            language=template.language,
        )
        session.add(row)
        await session.flush()
        return _prompt_template_to_domain(row)

    async def get_by_id(
        self, session: AsyncSession, template_id: uuid.UUID
    ) -> PromptTemplate | None:
        result = await session.execute(
            select(PromptTemplateORM).where(PromptTemplateORM.id == template_id)
        )
        row = result.scalar_one_or_none()
        return _prompt_template_to_domain(row) if row is not None else None

    async def deactivate(self, session: AsyncSession, template_id: uuid.UUID) -> None:
        result = await session.execute(
            select(PromptTemplateORM).where(PromptTemplateORM.id == template_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.is_active = False
        await session.flush()
