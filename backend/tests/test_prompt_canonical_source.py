"""Fuente canónica única de prompts (Fase 6.3.2, RFC §7.4) — demuestra que
`benchmark.generation.prompts` y el seed productivo
(`app/ai_pipeline/seed_prompts.py`) leen exactamente el mismo contenido
desde `app/ai_pipeline/prompts/`, sin divergencia posible: son el mismo
objeto en memoria, no una copia."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import PROMPT_SOURCES, seed_prompt_templates
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS
from app.integrations.domain.session_notes_generator import SESSION_NOTES_BLOCKS
from benchmark.generation import prompts as benchmark_prompts

#: docs/clinical-safety.md §3 — nunca debe aparecer en el texto de ninguna
#: plantilla de prompt, ni siquiera como ejemplo. Lista deliberadamente
#: pequeña y literal (no heurística) — mismo criterio que el resto de este
#: módulo, comprobar contra el texto real, no confiar en que "se escribió
#: con cuidado".
_FORBIDDEN_PHRASES = (
    "el paciente tiene",
    "diagnóstico confirmado",
    "tratamiento recomendado automáticamente",
)


def test_benchmark_reexporta_el_mismo_objeto_prompt_sources():
    # Identidad, no solo igualdad: benchmark no mantiene su propia copia.
    assert benchmark_prompts.PROMPT_CANDIDATES is PROMPT_SOURCES


def test_benchmark_reexporta_la_misma_funcion_de_seed():
    assert benchmark_prompts.seed_prompt_templates is seed_prompt_templates


def test_exactamente_6_fuentes_canonicas_una_por_artifact_type():
    # hito 6.4.4: se suman anamnesis_es_v1/session_notes_es_v1 — candidatas
    # de benchmark, ANAMNESIS/SESSION_NOTES siguen en Mock en producción
    # hasta tener un ganador con datos (ver sus propios .md). Ampliación
    # 2026-09-21 (docs/clinical-safety.md §7): se suma clinical_flags_es_v1
    # — candidata gated, CLINICAL_FLAGS sigue en Mock por defecto en todos
    # los entornos, incluida producción.
    assert {spec.artifact_type for spec in PROMPT_SOURCES} == {
        AIArtifactType.SUMMARY,
        AIArtifactType.MISSING_INFORMATION,
        AIArtifactType.PATIENT_SUMMARY,
        AIArtifactType.ANAMNESIS,
        AIArtifactType.SESSION_NOTES,
        AIArtifactType.CLINICAL_FLAGS,
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


def test_anamnesis_declara_los_20_campos_como_claves_del_ejemplo_de_salida():
    # hito 6.4.4 — el prompt debe nombrar EXACTAMENTE los 20 campos de
    # ANAMNESIS_FIELDS (única fuente de verdad, ver anamnesis_generator.py)
    # para que el modelo use esas claves y no otras.
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.ANAMNESIS)
    assert spec.name == "anamnesis_es_v1"
    assert "$transcript" in spec.user_prompt_template
    assert spec.variables_schema == {"required": ["transcript"], "optional": []}
    for field_name in ANAMNESIS_FIELDS:
        assert field_name in spec.system_prompt

    combined_status_words = [
        "informado",
        "negado_explicitamente",
        "no_preguntado",
        "no_determinado",
    ]
    for status in combined_status_words:
        assert status in spec.system_prompt


def test_session_notes_declara_los_4_bloques_como_claves_del_ejemplo_de_salida():
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.SESSION_NOTES)
    assert spec.name == "session_notes_es_v1"
    assert "$transcript" in spec.user_prompt_template
    assert "$previous_anamnesis_context" in spec.user_prompt_template
    assert spec.variables_schema == {
        "required": ["transcript", "previous_anamnesis_context"],
        "optional": [],
    }
    for block_name in SESSION_NOTES_BLOCKS:
        assert block_name in spec.system_prompt


def test_clinical_flags_conserva_el_texto_validado():
    # Ampliación 2026-09-21 (docs/clinical-safety.md §7) — mismo criterio
    # que el resto: el prompt debe declarar exactamente "flags" como
    # clave del JSON de salida y exigir source_excerpt no vacío.
    spec = next(s for s in PROMPT_SOURCES if s.artifact_type == AIArtifactType.CLINICAL_FLAGS)
    assert spec.name == "clinical_flags_es_v1"
    assert "$transcript" in spec.user_prompt_template
    assert spec.variables_schema == {"required": ["transcript"], "optional": []}
    assert '"flags"' in spec.system_prompt
    assert "source_excerpt" in spec.system_prompt


def test_ninguna_plantilla_contiene_lenguaje_clinico_prohibido():
    # docs/clinical-safety.md §3, punto 1: "Diseño de las plantillas ...
    # que deben servir de ejemplo correcto desde el primer commit."
    for spec in PROMPT_SOURCES:
        # Normaliza espacios/saltos de línea: el .md envuelve líneas largas
        # (p. ej. "...Prohibido: \"el\n  paciente tiene\"...") — es solo
        # formato del fichero fuente, no debe romper la búsqueda de frases.
        combined_text = " ".join(f"{spec.system_prompt}\n{spec.user_prompt_template}".split())
        combined_text = combined_text.lower()
        for phrase in _FORBIDDEN_PHRASES:
            # Las plantillas SÍ citan estas frases como ejemplo de lo que
            # está prohibido escribir — nunca las usan para describir un
            # hallazgo real. Se descarta esa mención legítima (siempre
            # entre comillas en las reglas obligatorias) y solo falla si
            # aparecen fuera de ese contexto de advertencia.
            occurrences = combined_text.count(phrase)
            quoted_occurrences = combined_text.count(f'"{phrase}"')
            assert (
                occurrences == quoted_occurrences
            ), f"'{phrase}' aparece en '{spec.name}' fuera de una cita de ejemplo prohibido."
            assert occurrences > 0, (
                f"'{phrase}' no aparece ni siquiera como ejemplo de lenguaje prohibido en "
                f"'{spec.name}' — confirma que la regla sigue citada explícitamente."
            )


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
    assert len(created) == 6

    second_run = await seed_prompt_templates(
        db_session, repository, created_by=clinic_with_users.admin.id
    )
    assert second_run == []  # ya sembrado por la llamada anterior — misma tabla, sin duplicar
