"""Fuente canónica única de las plantillas de prompt de producción — RFC
Git → seed → BD (docs/fase-6-rfc.md §7.4).

El texto de cada plantilla vive en el `.md` correspondiente de este mismo
directorio (revisable en PR como cualquier otro cambio de comportamiento
clínico, ver CLAUDE.md); este módulo solo declara la metadata estructurada
(`artifact_type`/`language`/`variables_schema`, que no tiene sitio natural
dentro de un `.md`) y sabe leer las dos secciones (`system_prompt`/
`user_prompt_template`) de cada fichero.

Único punto de verdad: tanto el seed de producción
(`app/ai_pipeline/seed_prompts.py`) como `benchmark/generation/prompts.py`
importan `PROMPT_SOURCES`/`seed_prompt_templates` desde aquí — nunca al
revés (`app/` no importa `benchmark/`, ver docs/generation-benchmark.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.prompt_template_repository import PromptTemplateRepository

_PROMPTS_DIR = Path(__file__).resolve().parent
_SYSTEM_MARKER = "## system_prompt"
_USER_MARKER = "## user_prompt_template"


class PromptSourceFormatError(Exception):
    """El `.md` no tiene las dos secciones esperadas — error de autoría,
    nunca se sustituye en silencio por una plantilla vacía."""

    def __init__(self, filename: str) -> None:
        super().__init__(
            f"'{filename}' no contiene las secciones '{_SYSTEM_MARKER}' y "
            f"'{_USER_MARKER}' — revisa el formato del fichero."
        )


def _read_sections(filename: str) -> tuple[str, str]:
    text = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    if _SYSTEM_MARKER not in text or _USER_MARKER not in text:
        raise PromptSourceFormatError(filename)

    _, after_system = text.split(_SYSTEM_MARKER, 1)
    system_prompt, user_prompt_template = after_system.split(_USER_MARKER, 1)
    return system_prompt.strip(), user_prompt_template.strip()


@dataclass(slots=True, frozen=True)
class PromptSourceSpec:
    name: str
    artifact_type: AIArtifactType
    language: str
    description: str
    system_prompt: str
    user_prompt_template: str
    variables_schema: dict[str, list[str]]


def _load(
    filename: str,
    *,
    name: str,
    artifact_type: AIArtifactType,
    language: str,
    description: str,
    variables_schema: dict[str, list[str]],
) -> PromptSourceSpec:
    system_prompt, user_prompt_template = _read_sections(filename)
    return PromptSourceSpec(
        name=name,
        artifact_type=artifact_type,
        language=language,
        description=description,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        variables_schema=variables_schema,
    )


_LANGUAGE_ES = "es"

#: Fuente canónica única — ver docstring del módulo. Cargada una vez al
#: importar el módulo (los `.md` no cambian en runtime).
PROMPT_SOURCES: tuple[PromptSourceSpec, ...] = (
    _load(
        "summary_es_v1.md",
        name="summary_es_v1",
        artifact_type=AIArtifactType.SUMMARY,
        language=_LANGUAGE_ES,
        description="Resumen profesional de consulta — candidata a producción (hito 6.3).",
        variables_schema={"required": ["transcript"], "optional": []},
    ),
    _load(
        "missing_information_es_v1.md",
        name="missing_information_es_v1",
        artifact_type=AIArtifactType.MISSING_INFORMATION,
        language=_LANGUAGE_ES,
        description="Información ausente — candidata a producción (hito 6.3).",
        variables_schema={"required": ["summary_text", "clinical_flags_text"], "optional": []},
    ),
    _load(
        "patient_summary_es_v1.md",
        name="patient_summary_es_v1",
        artifact_type=AIArtifactType.PATIENT_SUMMARY,
        language=_LANGUAGE_ES,
        description="Resumen en lenguaje llano para el paciente — candidata a producción (6.3).",
        variables_schema={"required": ["transcript", "summary_text"], "optional": []},
    ),
)


async def seed_prompt_templates(
    session: AsyncSession,
    repository: PromptTemplateRepository,
    *,
    created_by: uuid.UUID,
) -> list[PromptTemplate]:
    """Publica cada `PromptSourceSpec` como versión 1 activa si — y solo
    si — todavía no existe una plantilla activa para su
    `(artifact_type, language)`. Idempotente: nunca sobreescribe en
    silencio una plantilla activa existente (RFC §7.4, "nunca
    sustituciones silenciosas") — una segunda ejecución no crea nada
    nuevo."""
    created: list[PromptTemplate] = []
    for spec in PROMPT_SOURCES:
        existing = await repository.get_active(session, spec.artifact_type, spec.language)
        if existing is not None:
            continue
        template = PromptTemplate(
            id=uuid.uuid4(),
            name=spec.name,
            version=1,
            description=spec.description,
            system_prompt=spec.system_prompt,
            user_prompt_template=spec.user_prompt_template,
            variables_schema=spec.variables_schema,
            is_active=True,
            created_by=created_by,
            change_note="Seed inicial — fuente canónica app/ai_pipeline/prompts/ (hito 6.3).",
            created_at=datetime.now(UTC),
            artifact_type=spec.artifact_type,
            language=spec.language,
        )
        created.append(await repository.add(session, template))
    return created
