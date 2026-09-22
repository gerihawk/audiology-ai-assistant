"""RealClinicalFlagsGenerator (ampliación 2026-09-21, docs/clinical-safety.md
§7) — reabre deliberadamente la decisión "sin LLM" que cerraba ese
documento, con un generador real DISPONIBLE pero apagado por defecto
(`Settings.llm_provider_clinical_flags == "mock"` en todos los entornos,
incluida producción — ver `app/core/config.py`). Activarlo para cualquier
clínica real exige primero la validación clínica y legal que el propio
documento pide; mientras tanto, existe para poder probarlo (benchmark,
staging con datos ficticios) sin tocar el resto del sistema — mismo
patrón de aislamiento que ya protegía al mock (`ClinicalFlagsGenerator`,
`app/integrations/domain/clinical_flags_generator.py`).

Mismo patrón que `RealMissingInformationGenerator` (ver ese módulo), con
una diferencia crítica de seguridad: aquí SÍ hay `source_excerpt` por
señal, y a diferencia del schema general de `ClinicalFlagDraft`
(`source_excerpt: str | None`, nullable porque el mock nunca emite una
señal sin evidencia), este generador exige `source_excerpt` como string
no vacío en el schema JSON que le pide al proveedor — una señal sin cita
textual real nunca debería generarse, así que ni se le da al modelo la
opción de declarar "no tengo evidencia" para una señal que sí decide
reportar. Cualquier violación de esa forma se trata como
`INVALID_RESPONSE_FORMAT` (falla el intento, con la misma política de
reintentos que un JSON mal formado).

La verificación de que ese `source_excerpt` es una cita real de la
transcripción (no inventada) no vive aquí: la hace
`validate_generated_content`/`GroundingValidator`
(`app/ai_pipeline/domain/validation_pipeline.py`, `grounding.py`) después
de que `ClinicalFlagsStep.run()` devuelva `content` — el mismo chokepoint
por el que ya pasan `SUMMARY`/`PATIENT_SUMMARY`/`MISSING_INFORMATION`, sin
que este generador tenga que reimplementarlo. Igual para el lenguaje
prohibido (`SafetyValidator`, docs/clinical-safety.md §3).

`ruleset_name` nunca lo decide el LLM: es una constante de código, igual
que `RULESET_NAME` en `MockClinicalFlagsGenerator`, para poder auditar en
todo momento qué generador (regla fija vs. LLM real, y con qué versión de
plantilla) produjo cada señal, sin depender de que el proveedor lo
declare con honestidad."""

from __future__ import annotations

import re

from app.ai_pipeline.domain.entities import PromptTemplate, RenderContext
from app.ai_pipeline.domain.errors import AIGenerationFailureReason, TransientProviderError
from app.ai_pipeline.domain.prompt_renderer import PromptRenderer
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.language_model_provider import LanguageModelProvider, RenderedPrompt
from app.integrations.domain.session_context import SessionContext
from app.integrations.providers.json_response import parse_json_object

#: Identifica señales producidas por ESTE generador (LLM real) frente a
#: `demo_generic_v1` (el checklist basado en reglas) — ver docstring del
#: módulo. Versionar aquí, nunca reutilizar el nombre si cambia el
#: comportamiento (mismo criterio de `prompt_templates`, append-only).
RULESET_NAME = "clinical_flags_llm_es_v1"

#: `category` es de formato libre para el checklist (permite ampliarlo sin
#: tocar código), pero debe seguir siendo un identificador corto y estable
#: (snake_case), nunca una frase — para que sea comparable/auditable entre
#: sesiones y entre este generador y `demo_generic_v1`.
_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "source_excerpt": {"type": "string"},
                },
                "required": ["category", "description", "source_excerpt"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["flags"],
    "additionalProperties": False,
}


class RealClinicalFlagsGenerator:
    def __init__(
        self,
        provider: LanguageModelProvider,
        template: PromptTemplate,
        *,
        model: str,
        renderer: PromptRenderer | None = None,
    ) -> None:
        self._provider = provider
        self._template = template
        self._model = model
        self._renderer = renderer or PromptRenderer()

    async def generate(
        self, transcript: str, *, context: SessionContext
    ) -> list[ClinicalFlagDraft]:
        del context  # mismo criterio que el mock: no depende del contexto de sesión.
        rendered = self._renderer.render(
            self._template, RenderContext(variables={"transcript": transcript})
        )
        response = await self._provider.complete(
            RenderedPrompt(system=rendered.system_prompt, user=rendered.user_prompt),
            model=self._model,
            response_json_schema=_RESPONSE_JSON_SCHEMA,
        )
        content = parse_json_object(response.text)
        return _parse_flags(content.get("flags"))


def _parse_flags(raw_flags: object) -> list[ClinicalFlagDraft]:
    if not isinstance(raw_flags, list):
        raise TransientProviderError(
            "La respuesta del proveedor no incluye un campo 'flags' de tipo lista.",
            reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
        )
    flags: list[ClinicalFlagDraft] = []
    for raw_flag in raw_flags:
        if (
            not isinstance(raw_flag, dict)
            or not isinstance(raw_flag.get("category"), str)
            or not isinstance(raw_flag.get("description"), str)
            or not isinstance(raw_flag.get("source_excerpt"), str)
        ):
            raise TransientProviderError(
                "Un elemento de 'flags' no tiene la forma esperada (category/description/"
                "source_excerpt de tipo string).",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        category = raw_flag["category"]
        description = raw_flag["description"]
        source_excerpt = raw_flag["source_excerpt"]
        if not _CATEGORY_PATTERN.match(category):
            raise TransientProviderError(
                f"'category' debe ser un identificador snake_case corto, recibido: {category!r}.",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        if not description.strip():
            raise TransientProviderError(
                "'description' no puede estar vacía.",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        if not source_excerpt.strip():
            # Nunca se acepta una señal sin cita textual — ver docstring
            # del módulo: aquí no se permite `source_excerpt=None` como sí
            # ocurre en el schema general de `ClinicalFlagDraft`.
            raise TransientProviderError(
                "'source_excerpt' no puede estar vacío — una señal sin cita textual real "
                "nunca debe generarse.",
                reason=AIGenerationFailureReason.INVALID_RESPONSE_FORMAT,
            )
        flags.append(
            ClinicalFlagDraft(
                category=category,
                description=description,
                source_excerpt=source_excerpt,
                ruleset_name=RULESET_NAME,
            )
        )
    return flags
