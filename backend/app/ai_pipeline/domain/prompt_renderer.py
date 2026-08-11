"""`PromptRenderer` — sustitución determinista de variables en una
`PromptTemplate` ya seleccionada.

Fase 6.0.5 (docs/development-plan.md): infraestructura de prompts, sin
proveedor LLM real todavía. `PromptRenderer` no elige plantilla, no llama
a ningún proveedor y no registra nada — ver docs/ai-pipeline-architecture.md
§5 (tabla de responsabilidades) y §7.5 (almacenamiento de prompt
renderizado, decisión de un llamador futuro, no de este módulo).

Sintaxis de plantilla: `string.Template` (stdlib) con `$variable` /
`${variable}` — nunca `str.format`, porque los prompts reales incluirán
ejemplos de JSON con llaves literales (`{`/`}`) que `.format()`
interpretaría como placeholders.
"""

from __future__ import annotations

from string import Template

from app.ai_pipeline.domain.entities import PromptRenderResult, PromptTemplate, RenderContext


class PromptRenderError(Exception):
    """Base de los errores de render. Nunca se sustituye en silencio: toda
    variable obligatoria ausente, desconocida, mal tipada o plantilla con
    un placeholder no declarado en `variables_schema` aborta el render."""


class MissingRequiredVariableError(PromptRenderError):
    def __init__(self, missing: set[str]) -> None:
        super().__init__(f"Faltan variables obligatorias: {sorted(missing)}")
        self.missing = missing


class UnknownVariableError(PromptRenderError):
    def __init__(self, unknown: set[str]) -> None:
        super().__init__(f"Variables no declaradas en variables_schema: {sorted(unknown)}")
        self.unknown = unknown


class InvalidVariableTypeError(PromptRenderError):
    def __init__(self, name: str, value: object) -> None:
        super().__init__(f"La variable '{name}' debe ser str, recibido {type(value).__name__}.")
        self.name = name


class TemplatePlaceholderError(PromptRenderError):
    """El texto de la plantilla referencia un placeholder que no está en
    `context.variables` (desalineación entre `variables_schema` y el
    propio texto de la plantilla — error de autoría, no de la llamada)."""


class PromptRenderer:
    def render(self, template: PromptTemplate, context: RenderContext) -> PromptRenderResult:
        _validate_variable_types(context.variables)
        required, optional = _schema_variable_names(template.variables_schema)
        _validate_required_present(required, context.variables.keys())
        _validate_no_unknown_variables(required | optional, context.variables.keys())

        rendered_system = (
            _substitute(template.system_prompt, context.variables)
            if template.system_prompt is not None
            else None
        )
        rendered_user = _substitute(template.user_prompt_template, context.variables)

        return PromptRenderResult(
            system_prompt=rendered_system,
            user_prompt=rendered_user,
            variables_used=dict(context.variables),
            template_id=template.id,
            template_version=template.version,
        )


def _schema_variable_names(variables_schema: dict) -> tuple[set[str], set[str]]:
    required = set(variables_schema.get("required", []))
    optional = set(variables_schema.get("optional", []))
    return required, optional


def _validate_variable_types(variables: dict[str, str]) -> None:
    for name, value in variables.items():
        if not isinstance(value, str):
            raise InvalidVariableTypeError(name, value)


def _validate_required_present(required: set[str], provided: object) -> None:
    provided_set = set(provided)
    missing = required - provided_set
    if missing:
        raise MissingRequiredVariableError(missing)


def _validate_no_unknown_variables(declared: set[str], provided: object) -> None:
    unknown = set(provided) - declared
    if unknown:
        raise UnknownVariableError(unknown)


def _substitute(text: str, variables: dict[str, str]) -> str:
    try:
        return Template(text).substitute(variables)
    except KeyError as exc:
        raise TemplatePlaceholderError(
            f"La plantilla referencia el placeholder {exc} sin valor en variables."
        ) from exc
    except ValueError as exc:
        raise TemplatePlaceholderError(f"Placeholder inválido en la plantilla: {exc}") from exc
