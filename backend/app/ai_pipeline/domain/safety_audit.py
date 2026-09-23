"""Capa de auditoría LLM NO bloqueante sobre lenguaje clínico prohibido.

Cierre del Paso 2 del hallazgo bloqueante del red team
(docs/security/red-team-app-2026-09-22.md §A1). El Paso 1
(`app/ai_pipeline/domain/safety.py`) amplió el gate determinista que SÍ
bloquea la generación; esta capa es un segundo pase, deliberadamente sin
poder de bloqueo, sobre contenido que YA pasó ese gate — pensada para
capturar el caso que el Paso 1 documentó como no cerrable de forma
determinista (una afirmación diagnóstica sin ninguna palabra ancla, p. ej.
"Hipoacusia neurosensorial bilateral confirmada mediante audiometría").

Puro dominio: construye el prompt y parsea la respuesta, sin tocar red ni
base de datos. La orquestación (resolver el proveedor, llamarlo, capturar
fallos, persistir) vive en `app/ai_pipeline/safety_audit_task.py` — nunca
aquí, para poder testear el parseo/prompt sin mocks de infraestructura.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.domain.language_model_provider import RenderedPrompt
from app.integrations.providers.json_response import parse_json_object

#: Versionar aquí, nunca reutilizar el nombre si cambia el prompt o el
#: schema de respuesta (mismo criterio que `RULESET_NAME` en
#: `real_clinical_flags_generator.py`) — permite saber con qué versión de
#: prompt se generó cada fila de `ai_safety_audit_flags`.
PROMPT_VERSION = "safety_audit_es_v1"

RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "flagged": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "field": {"type": ["string", "null"]},
    },
    "required": ["flagged", "reasoning", "field"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "Eres un auditor de seguridad clínica. Tu única tarea es revisar el "
    "contenido generado por otro modelo de IA para un borrador de "
    "documentación audiológica y decidir si CUALQUIER parte de ese "
    "contenido presenta una inferencia de la IA como un hecho clínico "
    "establecido (un diagnóstico, una conclusión clínica dada por cierta), "
    "en vez de una señal que requiere valoración profesional humana. Esto "
    "aplica sin importar la forma exacta de las palabras: sinónimos, "
    "orden distinto, u otro idioma cuentan igual que la formulación más "
    "directa. No importa si el contenido es correcto o razonable "
    "clínicamente — importa únicamente si se presenta como un hecho ya "
    "establecido por la IA, en vez de como una señal a valorar por un "
    "profesional. Responde ÚNICAMENTE con el JSON pedido, nunca con texto "
    "adicional."
)


@dataclass(slots=True, frozen=True)
class SafetyAuditVerdict:
    flagged: bool
    reasoning: str
    field: str | None


def build_safety_audit_prompt(artifacts: dict[str, str]) -> RenderedPrompt:
    """`artifacts` es `{artifact_type: contenido_generado_como_texto}` — el
    llamador ya serializó cada contenido a texto (evita doble
    JSON-encoding: cada valor puede ser ya un JSON serializado, no se
    vuelve a envolver aquí) y ya filtró a solo artefactos que pasaron
    `validate_safety` (Paso 1); esta función no lo comprueba."""
    sections = "\n\n".join(
        f"### {artifact_type}\n{content}" for artifact_type, content in artifacts.items()
    )
    user = f"Contenido generado a revisar, por tipo de artefacto:\n\n{sections}"
    return RenderedPrompt(system=_SYSTEM_PROMPT, user=user)


def parse_safety_audit_response(raw_text: str) -> SafetyAuditVerdict:
    """Reutiliza `parse_json_object` (mismo parseo estricto que los
    `Real*Generator`) — cualquier excepción que lance (JSON inválido, no es
    un objeto) se propaga tal cual: el llamador (`safety_audit_task.py`) la
    captura junto con el resto de fallos del proveedor, nunca aquí."""
    data = parse_json_object(raw_text)
    flagged = data.get("flagged")
    reasoning = data.get("reasoning")
    field = data.get("field")
    if not isinstance(flagged, bool) or not isinstance(reasoning, str):
        raise ValueError(
            "Respuesta de auditoría con forma inválida: 'flagged' debe ser bool y "
            "'reasoning' debe ser str."
        )
    if field is not None and not isinstance(field, str):
        raise ValueError("Respuesta de auditoría con forma inválida: 'field' debe ser str o null.")
    return SafetyAuditVerdict(flagged=flagged, reasoning=reasoning, field=field)
