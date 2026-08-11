"""Tests de infraestructura (con DB real, sin red) para
`SqlAlchemyPromptTemplateRepository` — Fase 6.0.5."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.prompt_template_repository import (
    PromptTemplateNotFoundError,
    require_active_template,
)
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from tests.factories import ClinicWithUsers


def _template(
    *,
    created_by: uuid.UUID,
    name: str = "summary_es",
    version: int = 1,
    is_active: bool = True,
    artifact_type: AIArtifactType = AIArtifactType.SUMMARY,
    language: str = "es",
) -> PromptTemplate:
    return PromptTemplate(
        id=uuid.uuid4(),
        name=name,
        version=version,
        description="Plantilla de test",
        system_prompt="Eres un asistente clínico.",
        user_prompt_template="Resume: $transcript",
        variables_schema={"required": ["transcript"], "optional": []},
        is_active=is_active,
        created_by=created_by,
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=artifact_type,
        language=language,
    )


async def test_add_y_get_by_id_cargan_desde_base_de_datos(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()
    template = _template(created_by=clinic_with_users.admin.id)

    added = await repo.add(db_session, template)
    await db_session.commit()

    fetched = await repo.get_by_id(db_session, added.id)

    assert fetched is not None
    assert fetched.id == template.id
    assert fetched.artifact_type == AIArtifactType.SUMMARY
    assert fetched.language == "es"


async def test_get_active_by_name_sigue_funcionando_sin_cambios(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    """Compatibilidad absoluta: el método de la Fase 4.1 sigue intacto."""
    repo = SqlAlchemyPromptTemplateRepository()
    template = _template(created_by=clinic_with_users.admin.id, name="summary_es_legacy")
    await repo.add(db_session, template)
    await db_session.commit()

    fetched = await repo.get_active_by_name(db_session, "summary_es_legacy")

    assert fetched is not None
    assert fetched.name == "summary_es_legacy"


async def test_get_active_selecciona_por_artifact_type_y_language(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()
    summary_es = _template(
        created_by=clinic_with_users.admin.id,
        name="summary_es_v1",
        artifact_type=AIArtifactType.SUMMARY,
        language="es",
    )
    anamnesis_es = _template(
        created_by=clinic_with_users.admin.id,
        name="anamnesis_es_v1",
        artifact_type=AIArtifactType.ANAMNESIS,
        language="es",
    )
    await repo.add(db_session, summary_es)
    await repo.add(db_session, anamnesis_es)
    await db_session.commit()

    result = await repo.get_active(db_session, AIArtifactType.SUMMARY, "es")

    assert result is not None
    assert result.name == "summary_es_v1"


async def test_get_active_distingue_idioma(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()
    summary_es = _template(
        created_by=clinic_with_users.admin.id, name="summary_es_v1", language="es"
    )
    summary_en = _template(
        created_by=clinic_with_users.admin.id, name="summary_en_v1", language="en"
    )
    await repo.add(db_session, summary_es)
    await repo.add(db_session, summary_en)
    await db_session.commit()

    result_es = await repo.get_active(db_session, AIArtifactType.SUMMARY, "es")
    result_en = await repo.get_active(db_session, AIArtifactType.SUMMARY, "en")

    assert result_es is not None and result_es.name == "summary_es_v1"
    assert result_en is not None and result_en.name == "summary_en_v1"


async def test_get_active_devuelve_none_si_no_hay_plantilla_activa(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()

    result = await repo.get_active(db_session, AIArtifactType.ANAMNESIS, "fr")

    assert result is None


async def test_get_active_ignora_plantillas_inactivas(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()
    inactive = _template(
        created_by=clinic_with_users.admin.id, name="summary_es_draft", is_active=False
    )
    await repo.add(db_session, inactive)
    await db_session.commit()

    result = await repo.get_active(db_session, AIArtifactType.SUMMARY, "es")

    assert result is None


async def test_require_active_template_falla_explícitamente_si_no_existe(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()

    with pytest.raises(PromptTemplateNotFoundError) as exc_info:
        await require_active_template(db_session, repo, AIArtifactType.MISSING_INFORMATION, "es")

    assert exc_info.value.artifact_type == AIArtifactType.MISSING_INFORMATION
    assert exc_info.value.language == "es"


async def test_require_active_template_devuelve_la_plantilla_si_existe(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repo = SqlAlchemyPromptTemplateRepository()
    template = _template(created_by=clinic_with_users.admin.id, name="summary_es_v1")
    await repo.add(db_session, template)
    await db_session.commit()

    result = await require_active_template(db_session, repo, AIArtifactType.SUMMARY, "es")

    assert result.name == "summary_es_v1"


async def test_versionado_publicar_nueva_version_no_borra_la_anterior(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    """Publicar v2 activa desactiva v1 explícitamente (responsabilidad del
    llamador, no del repositorio) pero ambas siguen siendo consultables
    por id — append-only, ver docs/ai-pipeline-architecture.md §7.4."""
    repo = SqlAlchemyPromptTemplateRepository()
    v1 = _template(created_by=clinic_with_users.admin.id, name="summary_es", version=1)
    added_v1 = await repo.add(db_session, v1)
    await db_session.commit()

    await repo.deactivate(db_session, added_v1.id)
    v2 = _template(created_by=clinic_with_users.admin.id, name="summary_es", version=2)
    added_v2 = await repo.add(db_session, v2)
    await db_session.commit()

    still_v1 = await repo.get_by_id(db_session, added_v1.id)
    still_v2 = await repo.get_by_id(db_session, added_v2.id)

    assert still_v1 is not None and still_v1.version == 1 and still_v1.is_active is False
    assert still_v2 is not None and still_v2.version == 2 and still_v2.is_active is True

    active = await repo.get_active(db_session, AIArtifactType.SUMMARY, "es")
    assert active is not None and active.version == 2
