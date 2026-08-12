"""Fuente canónica única de prompts (Fase 6.3.2, RFC §7.4) — demuestra que
`benchmark.generation.prompts` y el seed productivo
(`app/ai_pipeline/seed_prompts.py`) leen exactamente el mismo contenido
desde `app/ai_pipeline/prompts/`, sin divergencia posible: son el mismo
objeto en memoria, no una copia."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import PROMPT_SOURCES, seed_prompt_templates
from benchmark.generation import prompts as benchmark_prompts


def test_benchmark_reexporta_el_mismo_objeto_prompt_sources():
    # Identidad, no solo igualdad: benchmark no mantiene su propia copia.
    assert benchmark_prompts.PROMPT_CANDIDATES is PROMPT_SOURCES


def test_benchmark_reexporta_la_misma_funcion_de_seed():
    assert benchmark_prompts.seed_prompt_templates is seed_prompt_templates


def test_exactamente_3_fuentes_canonicas_una_por_artifact_type():
    assert {spec.artifact_type for spec in PROMPT_SOURCES} == {
        AIArtifactType.SUMMARY,
        AIArtifactType.MISSING_INFORMATION,
        AIArtifactType.PATIENT_SUMMARY,
    }
    assert all(spec.language == "es" for spec in PROMPT_SOURCES)


def test_summary_conserva_el_texto_validado_en_el_benchmark():
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.SUMMARY)
    assert spec.name == "summary_es_v1"
    assert spec.system_prompt.startswith(
        "Eres un asistente de documentación clínica para audioprotesistas."
    )
    assert spec.system_prompt.endswith('{"text": "<resumen>"}.')
    assert "$transcript" in spec.user_prompt_template
    assert spec.variables_schema == {"required": ["transcript"], "optional": []}


def test_missing_information_conserva_el_texto_validado_en_el_benchmark():
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.MISSING_INFORMATION)
    assert "$summary_text" in spec.user_prompt_template
    assert "$clinical_flags_text" in spec.user_prompt_template
    assert "$transcript" not in spec.user_prompt_template
    assert spec.variables_schema == {
        "required": ["summary_text", "clinical_flags_text"],
        "optional": [],
    }


def test_patient_summary_conserva_el_texto_validado_en_el_benchmark():
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.PATIENT_SUMMARY)
    assert "$transcript" in spec.user_prompt_template
    assert "$summary_text" in spec.user_prompt_template
    assert spec.variables_schema == {"required": ["transcript", "summary_text"], "optional": []}


async def test_seed_desde_el_import_de_benchmark_puebla_la_misma_tabla_que_el_de_app(
    db_session, clinic_with_users
):
    """Sembrar vía `benchmark.generation.prompts.seed_prompt_templates`
    dispone la misma plantilla activa que consultaría
    `app/ai_pipeline/seed_prompts.py` — porque es literalmente la misma
    función y la misma tabla, nunca una copia paralela."""
    repository = SqlAlchemyPromptTemplateRepository()

    created = await benchmark_prompts.seed_prompt_templates(
        db_session, repository, created_by=clinic_with_users.admin.id
    )
    await db_session.commit()
    assert len(created) == 3

    second_run = await seed_prompt_templates(
        db_session, repository, created_by=clinic_with_users.admin.id
    )
    assert second_run == []  # ya sembrado por la llamada anterior — misma tabla, sin duplicar
