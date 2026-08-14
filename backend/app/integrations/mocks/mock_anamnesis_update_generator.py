"""MockAnamnesisUpdateGenerator — Hito 6.5.2, RFC técnico de 6.5 §4-§5.

Determinista, sin LLM, sin red: mismo criterio que `MockAnamnesisGenerator`
(keywords reconocidas explícitamente, nunca NLP general). No pretende ser
un parser clínico productivo — demuestra el contrato de
`AnamnesisUpdateGenerator` con una matriz mínima y legible.

Regla de seguridad clínica (única, aplicada uniformemente a los cinco
campos reconocidos en `_FIELD_TRIGGERS`, ver RFC técnico de 6.5 §7):

- si el campo está en un estado de laguna (`no_preguntado`/
  `no_determinado`) en `previous_anamnesis`, cualquier mención reconocida
  se propone como `fills_gap`, sin necesitar marcador alguno — no había
  nada que contradecir;
- si el campo ya está `informado`/`negado_explicitamente`, una mención
  reconocida SOLO se propone como `explicit_correction` cuando el
  transcript contiene además uno de los marcadores explícitos de
  `_CORRECTION_MARKERS`; sin marcador, no se propone ningún cambio —
  nunca se infiere una corrección de una frase aislada, sea o no
  compatible con el valor previo (cubre por igual "contradicción sin
  marcador", "reafirmación" e "información compatible": las tres son
  indistinguibles para un Mock sin NLP real, y las tres deben resultar en
  "sin cambio" según RFC técnico de 6.5 §4.8).

`source_excerpt` es siempre una ventana literal del transcript ACTUAL
alrededor de la keyword que disparó el campo — mismo patrón que
`mock_anamnesis_generator.py`/`mock_clinical_flags_generator.py`. Nunca
se copia ni se deriva de `previous_anamnesis`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.integrations.domain.anamnesis_generator import AnamnesisFieldStatus
from app.integrations.domain.anamnesis_update_generator import (
    AnamnesisFieldUpdate,
    AnamnesisUpdateReason,
    AnamnesisUpdateResult,
)
from app.integrations.domain.session_context import SessionContext

#: Caracteres de contexto a cada lado del match — mismo valor que
#: `mock_anamnesis_generator._EXCERPT_PADDING`.
_EXCERPT_PADDING = 60

_GAP_STATUSES = frozenset({AnamnesisFieldStatus.NO_PREGUNTADO, AnamnesisFieldStatus.NO_DETERMINADO})

#: Marcadores explícitos de corrección reconocidos (RFC técnico de 6.5
#: §5 del encargo de 6.5.2) — deliberadamente un conjunto cerrado y
#: pequeño, nunca inferencia semántica general.
_CORRECTION_MARKERS: tuple[str, ...] = ("quiero corregir", "me equivoqué", "antes dije")


@dataclass(slots=True, frozen=True)
class _FieldTrigger:
    """Una keyword reconocida (buscada en minúsculas) y lo que
    representaría si llega a proponerse como update — el `reason` real
    (`fills_gap`/`explicit_correction`) lo decide `_propose_update` según
    el `previous_status` real, nunca este trigger."""

    keyword: str
    field_name: str
    candidate_status: AnamnesisFieldStatus
    candidate_value: str


#: Vocabulario cerrado reconocido por el Mock — mismo criterio que
#: `MockAnamnesisGenerator._extract_fields` ("acúfenos"/"niega vértigo").
#: `"acúfenos"` reutiliza literalmente la keyword ya reconocida por
#: `MockAnamnesisGenerator`, para poder reutilizar `FIRST_VISIT_TRANSCRIPT`
#: sin duplicar transcripts sintéticos (RFC técnico de 6.5 §10 del
#: encargo de 6.5.2).
_FIELD_TRIGGERS: tuple[_FieldTrigger, ...] = (
    _FieldTrigger(
        "acúfenos",
        "tinnitus",
        AnamnesisFieldStatus.INFORMADO,
        "Acúfenos referidos por el paciente.",
    ),
    _FieldTrigger(
        "pitido leve en el oído derecho",
        "tinnitus",
        AnamnesisFieldStatus.INFORMADO,
        "Pitido leve en oído derecho.",
    ),
    _FieldTrigger(
        "niega vértigo",
        "vertigo_o_inestabilidad",
        AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
        "El paciente niega vértigo.",
    ),
    _FieldTrigger(
        "noto algo de vértigo",
        "vertigo_o_inestabilidad",
        AnamnesisFieldStatus.INFORMADO,
        "El paciente refiere vértigo.",
    ),
    _FieldTrigger(
        "más intenso",
        "otalgia",
        AnamnesisFieldStatus.INFORMADO,
        "Dolor en oído derecho, más intenso.",
    ),
)


def _excerpt_around(transcript: str, lowered: str, keyword: str) -> str:
    """Ventana real de contexto alrededor de `keyword` — ver docstring del
    módulo. La posición se busca en minúsculas pero el recorte final se
    toma del transcript ORIGINAL, para que el excerpt siga siendo una
    cita literal."""
    start = lowered.find(keyword)
    end = start + len(keyword)
    window_start = max(0, start - _EXCERPT_PADDING)
    window_end = min(len(transcript), end + _EXCERPT_PADDING)
    return transcript[window_start:window_end]


def _propose_update(
    trigger: _FieldTrigger, transcript: str, lowered: str, previous_anamnesis: dict[str, Any]
) -> AnamnesisFieldUpdate | None:
    if trigger.keyword not in lowered:
        return None

    baseline_field = previous_anamnesis.get(trigger.field_name) or {}
    previous_value = baseline_field.get("value", "")
    previous_status = AnamnesisFieldStatus(
        baseline_field.get("status", AnamnesisFieldStatus.NO_PREGUNTADO.value)
    )

    if previous_status in _GAP_STATUSES:
        reason = AnamnesisUpdateReason.FILLS_GAP
    else:
        if not any(marker in lowered for marker in _CORRECTION_MARKERS):
            return None  # sin marcador explícito, nunca se infiere una corrección.
        reason = AnamnesisUpdateReason.EXPLICIT_CORRECTION

    return AnamnesisFieldUpdate(
        field_name=trigger.field_name,
        previous_value=previous_value,
        previous_status=previous_status,
        proposed_value=trigger.candidate_value,
        proposed_status=trigger.candidate_status,
        source_excerpt=_excerpt_around(transcript, lowered, trigger.keyword),
        reason=reason,
    )


class MockAnamnesisUpdateGenerator:
    async def generate(
        self,
        transcript: str,
        previous_anamnesis: dict[str, Any],
        *,
        context: SessionContext,
    ) -> AnamnesisUpdateResult:
        lowered = transcript.lower()
        updates = [
            update
            for trigger in _FIELD_TRIGGERS
            if (update := _propose_update(trigger, transcript, lowered, previous_anamnesis))
            is not None
        ]
        return AnamnesisUpdateResult(updates=updates)
