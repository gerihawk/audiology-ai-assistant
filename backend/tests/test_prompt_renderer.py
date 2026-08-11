"""Tests puros de dominio (sin DB, sin red) para `PromptRenderer` — Fase
6.0.5. Ver docs/development-plan.md y app/ai_pipeline/domain/prompt_renderer.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate, RenderContext
from app.ai_pipeline.domain.prompt_renderer import (
    InvalidVariableTypeError,
    MissingRequiredVariableError,
    PromptRenderer,
    TemplatePlaceholderError,
    UnknownVariableError,
)


def _template(
    *,
    system_prompt: str | None = "Eres un asistente clínico para $clinic_name.",
    user_prompt_template: str = "Resume esta transcripción: $transcript",
    variables_schema: dict | None = None,
    version: int = 1,
    artifact_type: AIArtifactType = AIArtifactType.SUMMARY,
    language: str = "es",
) -> PromptTemplate:
    return PromptTemplate(
        id=uuid.uuid4(),
        name="summary_es",
        version=version,
        description=None,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        variables_schema=(
            variables_schema
            if variables_schema is not None
            else {"required": ["transcript", "clinic_name"], "optional": []}
        ),
        is_active=True,
        created_by=uuid.uuid4(),
        change_note=None,
        created_at=datetime.now(UTC),
        artifact_type=artifact_type,
        language=language,
    )


def test_render_correcto_sustituye_system_y_user_prompt():
    template = _template()
    renderer = PromptRenderer()

    result = renderer.render(
        template,
        RenderContext(
            variables={"transcript": "Paciente refiere acúfenos.", "clinic_name": "Clínica Test"}
        ),
    )

    assert result.system_prompt == "Eres un asistente clínico para Clínica Test."
    assert result.user_prompt == "Resume esta transcripción: Paciente refiere acúfenos."


def test_render_versión_correcta_en_el_resultado():
    template = _template(version=7)
    renderer = PromptRenderer()

    result = renderer.render(
        template, RenderContext(variables={"transcript": "texto", "clinic_name": "X"})
    )

    assert result.template_version == 7
    assert result.template_id == template.id


def test_render_variables_used_refleja_lo_realmente_pasado():
    template = _template()
    renderer = PromptRenderer()
    variables = {"transcript": "texto", "clinic_name": "X"}

    result = renderer.render(template, RenderContext(variables=variables))

    assert result.variables_used == variables


def test_variable_obligatoria_ausente_falla():
    template = _template()
    renderer = PromptRenderer()

    with pytest.raises(MissingRequiredVariableError) as exc_info:
        renderer.render(template, RenderContext(variables={"transcript": "texto"}))

    assert exc_info.value.missing == {"clinic_name"}


def test_variable_desconocida_falla_sin_sustitución_silenciosa():
    template = _template()
    renderer = PromptRenderer()

    with pytest.raises(UnknownVariableError) as exc_info:
        renderer.render(
            template,
            RenderContext(
                variables={
                    "transcript": "texto",
                    "clinic_name": "X",
                    "campo_no_declarado": "inyectado",
                }
            ),
        )

    assert exc_info.value.unknown == {"campo_no_declarado"}


def test_variable_declarada_como_opcional_se_acepta():
    template = _template(
        system_prompt=None,
        user_prompt_template="Resumen: $transcript ($extra)",
        variables_schema={"required": ["transcript"], "optional": ["extra"]},
    )
    renderer = PromptRenderer()

    result = renderer.render(
        template, RenderContext(variables={"transcript": "texto", "extra": "nota"})
    )

    assert result.user_prompt == "Resumen: texto (nota)"


def test_variable_mal_tipada_falla():
    template = _template()
    renderer = PromptRenderer()

    with pytest.raises(InvalidVariableTypeError):
        renderer.render(
            template,
            RenderContext(variables={"transcript": "texto", "clinic_name": 123}),  # type: ignore[dict-item]
        )


def test_placeholder_no_declarado_en_texto_de_plantilla_falla():
    template = _template(
        user_prompt_template="Resumen: $transcript $typo_no_declarado",
        variables_schema={"required": ["transcript"], "optional": []},
    )
    renderer = PromptRenderer()

    with pytest.raises(TemplatePlaceholderError):
        renderer.render(template, RenderContext(variables={"transcript": "texto"}))


def test_render_es_determinista():
    template = _template()
    renderer = PromptRenderer()
    context = RenderContext(variables={"transcript": "texto fijo", "clinic_name": "Clínica X"})

    first = renderer.render(template, context)
    second = renderer.render(template, context)

    assert first == second


def test_prompt_template_compatible_con_campos_ya_existentes():
    """Construir un PromptTemplate con exactamente los campos de la Fase
    4.1 (más los nuevos de la 6.0.5) no rompe nada — compatibilidad
    absoluta exigida por el encargo de la Fase 6.0.5."""
    template = _template()

    assert template.name == "summary_es"
    assert template.is_active is True
    assert template.variables_schema["required"] == ["transcript", "clinic_name"]
    assert template.artifact_type == AIArtifactType.SUMMARY
    assert template.language == "es"


def test_render_sin_system_prompt_devuelve_none():
    template = _template(system_prompt=None)
    renderer = PromptRenderer()

    result = renderer.render(
        template, RenderContext(variables={"transcript": "texto", "clinic_name": "X"})
    )

    assert result.system_prompt is None
