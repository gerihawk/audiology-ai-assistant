"""`AIPipelineService._require_prompt_template` (Fase 6.3.3, RFC §7.4) —
resuelve la plantilla activa antes de invocar cualquier proveedor real.
Cableado completo en `_build_steps()` (junto al routing por artifact_type)
llega en el hito 6.3.4/6.3.7 — este archivo cubre el mecanismo de
resolución en aislamiento, con BD real y sin proveedor.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import seed_prompt_templates
from app.ai_pipeline.service import AIPipelineService
from app.core.exceptions import ConflictError
from tests.factories import ClinicWithUsers


async def test_devuelve_la_plantilla_activa_cuando_existe(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()

    service = AIPipelineService(db_session)
    template = await service._require_prompt_template(AIArtifactType.SUMMARY, "es")

    assert isinstance(template, PromptTemplate)
    assert template.artifact_type == AIArtifactType.SUMMARY
    assert template.language == "es"
    assert template.is_active is True


async def test_falla_con_conflicterror_explicito_si_falta_la_plantilla(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    # Sin seed: no existe ninguna plantilla activa todavía.
    service = AIPipelineService(db_session)

    try:
        await service._require_prompt_template(AIArtifactType.MISSING_INFORMATION, "es")
        raise AssertionError("Debía lanzar ConflictError")
    except ConflictError as exc:
        assert "missing_information" in str(exc)
        assert "es" in str(exc)


async def test_falla_para_idioma_sin_plantilla_aunque_el_artifact_type_si_tenga(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()

    service = AIPipelineService(db_session)

    try:
        await service._require_prompt_template(AIArtifactType.SUMMARY, "en")
        raise AssertionError("Debía lanzar ConflictError")
    except ConflictError:
        pass
