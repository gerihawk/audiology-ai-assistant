"""Plantillas de prompt candidatas del benchmark de generación — encargo
de la Fase 6.2 §12-13: "El benchmark debe utilizar la infraestructura
oficial: `PromptTemplateRepository` + `PromptRenderer`. No crear prompts
hardcodeados dentro del runner."

Estas son las MISMAS plantillas candidatas a producción (hito 6.3, ver
docs/fase-6-rfc.md §10) — no una copia de benchmark. Contenido alineado
con docs/clinical-safety.md §2-3 (lenguaje obligatorio/prohibido): el
texto no confiable (transcripción, resumen) solo ocupa variables
declaradas del `user_prompt_template`, nunca el `system_prompt` — ver
docs/privacy-and-security.md §11 (fila "Inyección de prompt").

`PATIENT_SUMMARY` declara `summary_text` como variable **obligatoria**
(no opcional) aunque la RFC diga "cuando esté disponible en la
ejecución": `PromptRenderer` usa `string.Template.substitute` (estricto,
sin sustitución condicional) — un caso sin resumen disponible pasa
`summary_text=""`, nunca omite la variable."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactType, PromptTemplate
from app.ai_pipeline.domain.prompt_template_repository import PromptTemplateRepository

_LANGUAGE_ES = "es"

_SUMMARY_SYSTEM_PROMPT = """Eres un asistente de documentación clínica para audioprotesistas.
Tu única tarea es redactar un resumen profesional breve de una consulta
de audiología a partir de su transcripción.

Reglas obligatorias:
- Usa exclusivamente información que aparezca explícitamente en la
  transcripción. Nunca inventes ni infieras datos que no se mencionaron.
- Nunca uses lenguaje diagnóstico ni de tratamiento. Prohibido: "el
  paciente tiene", "diagnóstico confirmado", "tratamiento recomendado
  automáticamente", o cualquier formulación que presente una inferencia
  como hecho clínico establecido.
- Usa en su lugar expresiones no diagnósticas cuando corresponda: "señal
  que requiere valoración profesional", "información que convendría
  ampliar", "posible motivo de derivación según el protocolo
  configurado", "hipótesis no diagnóstica".
- No calcules ni sugieras grados de pérdida auditiva, ni recomiendes
  productos, ajustes de audífono ni tratamientos.
- Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni
  markdown, con exactamente esta forma: {"text": "<resumen>"}."""

_SUMMARY_USER_PROMPT = """Transcripción de la consulta:

$transcript

Redacta el resumen profesional siguiendo estrictamente las reglas
anteriores. Devuelve solo el JSON."""

_MISSING_INFORMATION_SYSTEM_PROMPT = """\
Eres un asistente de documentación clínica para audioprotesistas. Tu
tarea es identificar información clínicamente relevante que NO se
recogió durante la consulta, a partir de un resumen y de las señales de
alerta ya detectadas.

Reglas obligatorias:
- Basa tus sugerencias únicamente en lo que aparece en el resumen y las
  señales de alerta proporcionados. Nunca inventes contenido clínico
  nuevo.
- Nunca uses lenguaje diagnóstico ni de tratamiento (prohibido: "el
  paciente tiene", "diagnóstico confirmado", "tratamiento recomendado
  automáticamente").
- Cada elemento propone un tema ausente (topic) y una pregunta sugerida
  (suggested_question) que el profesional podría plantear en la
  siguiente consulta.
- Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni
  markdown, con exactamente esta forma: {"items": [{"topic": "...",
  "suggested_question": "..."}]}. Si no falta información relevante,
  devuelve {"items": []}."""

_MISSING_INFORMATION_USER_PROMPT = """Resumen de la consulta:
$summary_text

Señales de alerta detectadas:
$clinical_flags_text

Identifica la información clínicamente relevante que falta, siguiendo
estrictamente las reglas anteriores. Devuelve solo el JSON."""

_PATIENT_SUMMARY_SYSTEM_PROMPT = """\
Eres un asistente de documentación clínica para audioprotesistas. Tu
tarea es redactar una explicación breve, en lenguaje llano y
comprensible para el paciente, de lo tratado en la consulta — distinta
del resumen técnico dirigido al profesional.

Reglas obligatorias:
- Usa exclusivamente información que aparezca explícitamente en la
  transcripción (y, si se aporta, en el resumen técnico). Nunca inventes
  ni infieras datos que no se mencionaron.
- Nunca uses lenguaje diagnóstico ni de tratamiento (prohibido: "el
  paciente tiene", "diagnóstico confirmado", "tratamiento recomendado
  automáticamente"). No transformes señales, sospechas o incertidumbre
  clínica en diagnósticos ni recomendaciones de tratamiento.
- Usa un lenguaje sencillo, cercano y sin jerga técnica innecesaria.
- Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni
  markdown, con exactamente esta forma: {"text": "<explicación>"}."""

_PATIENT_SUMMARY_USER_PROMPT = """Transcripción de la consulta:
$transcript

Resumen técnico de referencia (vacío si no está disponible):
$summary_text

Redacta la explicación para el paciente siguiendo estrictamente las
reglas anteriores. Devuelve solo el JSON."""


@dataclass(slots=True, frozen=True)
class PromptCandidateSpec:
    name: str
    artifact_type: AIArtifactType
    language: str
    description: str
    system_prompt: str
    user_prompt_template: str
    variables_schema: dict[str, list[str]]


PROMPT_CANDIDATES: tuple[PromptCandidateSpec, ...] = (
    PromptCandidateSpec(
        name="summary_es_v1",
        artifact_type=AIArtifactType.SUMMARY,
        language=_LANGUAGE_ES,
        description="Resumen profesional de consulta — candidata a producción (hito 6.3).",
        system_prompt=_SUMMARY_SYSTEM_PROMPT,
        user_prompt_template=_SUMMARY_USER_PROMPT,
        variables_schema={"required": ["transcript"], "optional": []},
    ),
    PromptCandidateSpec(
        name="missing_information_es_v1",
        artifact_type=AIArtifactType.MISSING_INFORMATION,
        language=_LANGUAGE_ES,
        description="Información ausente — candidata a producción (hito 6.3).",
        system_prompt=_MISSING_INFORMATION_SYSTEM_PROMPT,
        user_prompt_template=_MISSING_INFORMATION_USER_PROMPT,
        variables_schema={"required": ["summary_text", "clinical_flags_text"], "optional": []},
    ),
    PromptCandidateSpec(
        name="patient_summary_es_v1",
        artifact_type=AIArtifactType.PATIENT_SUMMARY,
        language=_LANGUAGE_ES,
        description="Resumen en lenguaje llano para el paciente — candidata a producción (6.3).",
        system_prompt=_PATIENT_SUMMARY_SYSTEM_PROMPT,
        user_prompt_template=_PATIENT_SUMMARY_USER_PROMPT,
        variables_schema={"required": ["transcript", "summary_text"], "optional": []},
    ),
)


async def seed_prompt_templates(
    session: AsyncSession,
    repository: PromptTemplateRepository,
    *,
    created_by: uuid.UUID,
) -> list[PromptTemplate]:
    """Publica cada `PromptCandidateSpec` como versión 1 activa si — y
    solo si — todavía no existe una plantilla activa para su
    `(artifact_type, language)`. Idempotente: nunca sobreescribe en
    silencio una plantilla activa existente (encargo §13, "nunca
    sustituciones silenciosas") — una segunda ejecución no crea nada
    nuevo."""
    created: list[PromptTemplate] = []
    for spec in PROMPT_CANDIDATES:
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
            change_note="Seed inicial — benchmark de generación (hito 6.2).",
            created_at=datetime.now(UTC),
            artifact_type=spec.artifact_type,
            language=spec.language,
        )
        created.append(await repository.add(session, template))
    return created
