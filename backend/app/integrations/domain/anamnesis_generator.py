"""Puerto AnamnesisGenerator.

Último paso del grafo: recibe tanto la transcripción (texto fuente) como
la información ausente ya identificada, para producir un borrador
consciente de sus propias lagunas. Ver docs/ai-pipeline-architecture.md
§1.4 y §6.1.

`ANAMNESIS_FIELDS` son los 20 campos rellenables por IA de
docs/data-model.md §3 (campos 1-20). Los campos 21
(`informacion_ausente`) y 22 (`observaciones_profesional`) **no** forman
parte del contenido generado: el primero es una lista calculada por el
backend a partir de los estados de estos 20 campos, el segundo es
exclusivamente editable por el profesional — ninguno de los dos es salida
de `AnamnesisGenerator`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.integrations.domain.missing_information_generator import MissingInfoItem
from app.integrations.domain.session_context import SessionContext


class AnamnesisFieldStatus(StrEnum):
    INFORMADO = "informado"
    NEGADO_EXPLICITAMENTE = "negado_explicitamente"
    NO_PREGUNTADO = "no_preguntado"
    NO_DETERMINADO = "no_determinado"


ANAMNESIS_FIELDS: tuple[str, ...] = (
    "motivo_consulta",
    "percepcion_subjetiva_perdida_auditiva",
    "inicio_y_evolucion",
    "lateralidad",
    "antecedentes_familiares",
    "antecedentes_otologicos",
    "infecciones",
    "cirugias",
    "exposicion_ruido",
    "medicacion_ototoxica_declarada",
    "tinnitus",
    "vertigo_o_inestabilidad",
    "otalgia",
    "otorrea",
    "sensacion_plenitud",
    "dificultades_comprension",
    "situaciones_auditivas_problematicas",
    "uso_previo_audifonos",
    "expectativas",
    "impacto_social_laboral_familiar",
)


@dataclass(slots=True, frozen=True)
class AnamnesisFieldValue:
    value: str
    status: AnamnesisFieldStatus


@dataclass(slots=True, frozen=True)
class AnamnesisDraft:
    fields: dict[str, AnamnesisFieldValue]


class AnamnesisGenerator(Protocol):
    async def generate(
        self,
        transcript: str,
        missing_information: list[MissingInfoItem],
        *,
        context: SessionContext,
    ) -> AnamnesisDraft: ...
