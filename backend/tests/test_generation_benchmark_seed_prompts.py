"""Tests de infraestructura (DB real, sin red) para
`seed_prompt_templates` — Fase 6.2."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from benchmark.generation.prompts import PROMPT_CANDIDATES, seed_prompt_templates
from tests.factories import ClinicWithUsers


async def test_primera_ejecucion_crea_las_6_plantillas(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repository = SqlAlchemyPromptTemplateRepository()

    created = await seed_prompt_templates(
        db_session, repository, created_by=clinic_with_users.admin.id
    )
    await db_session.commit()

    # hito 6.4.4: anamnesis_es_v1/session_notes_es_v1 se siembran igual que
    # las 3 anteriores — sembrar la plantilla nunca la activa en
    # producción, eso lo decide `service.py` (sigue en Mock hasta tener un
    # ganador del benchmark con datos). Ampliación 2026-09-21
    # (docs/clinical-safety.md §7): se suma clinical_flags_es_v1, mismo
    # criterio — sembrarla nunca activa el generador real, eso lo decide
    # `Settings.llm_provider_clinical_flags` ("mock" por defecto).
    assert len(created) == 6
    assert {t.artifact_type for t in created} == {
        AIArtifactType.SUMMARY,
        AIArtifactType.MISSING_INFORMATION,
        AIArtifactType.PATIENT_SUMMARY,
        AIArtifactType.ANAMNESIS,
        AIArtifactType.SESSION_NOTES,
        AIArtifactType.CLINICAL_FLAGS,
    }
    assert all(t.is_active for t in created)
    assert all(t.version == 1 for t in created)


async def test_segunda_ejecucion_es_idempotente(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repository = SqlAlchemyPromptTemplateRepository()

    await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)
    await db_session.commit()

    second_run = await seed_prompt_templates(
        db_session, repository, created_by=clinic_with_users.admin.id
    )

    assert second_run == []


async def test_nunca_sobreescribe_una_plantilla_activa_existente(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
):
    repository = SqlAlchemyPromptTemplateRepository()
    await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)
    await db_session.commit()

    active_before = await repository.get_active(db_session, AIArtifactType.SUMMARY, "es")

    await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)

    active_after = await repository.get_active(db_session, AIArtifactType.SUMMARY, "es")
    assert active_after.id == active_before.id
    assert active_after.version == 1


def test_las_6_plantillas_declaran_sus_variables_correctamente():
    # Regresión del bug corregido en runner.py: `missing_information`
    # nunca debe declarar "transcript" (no lo usa su plantilla).
    by_type = {spec.artifact_type: spec for spec in PROMPT_CANDIDATES}

    summary_vars = set(by_type[AIArtifactType.SUMMARY].variables_schema["required"])
    assert "transcript" in summary_vars

    missing_info_vars = set(
        by_type[AIArtifactType.MISSING_INFORMATION].variables_schema["required"]
    )
    assert "transcript" not in missing_info_vars
    assert missing_info_vars == {"summary_text", "clinical_flags_text"}

    patient_summary_vars = set(by_type[AIArtifactType.PATIENT_SUMMARY].variables_schema["required"])
    assert patient_summary_vars == {"transcript", "summary_text"}

    # hito 6.4.4 — anamnesis solo necesita transcript (mismo criterio que
    # missing_information con `target`: no se añade una variable que el
    # dataset de 2 casos todavía no necesita, ver anamnesis_es_v1.md).
    anamnesis_vars = set(by_type[AIArtifactType.ANAMNESIS].variables_schema["required"])
    assert anamnesis_vars == {"transcript"}

    # session_notes exige previous_anamnesis_context siempre presente
    # (nunca opcional): PromptRenderer usa Template.substitute, que falla
    # si el placeholder no está en variables — ver session_notes_es_v1.md.
    session_notes_vars = set(by_type[AIArtifactType.SESSION_NOTES].variables_schema["required"])
    assert session_notes_vars == {"transcript", "previous_anamnesis_context"}

    # Ampliación 2026-09-21 (docs/clinical-safety.md §7) — clinical_flags
    # solo necesita transcript, mismo criterio que anamnesis.
    clinical_flags_vars = set(by_type[AIArtifactType.CLINICAL_FLAGS].variables_schema["required"])
    assert clinical_flags_vars == {"transcript"}
