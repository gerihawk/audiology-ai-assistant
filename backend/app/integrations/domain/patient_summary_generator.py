"""Puerto PatientSummaryGenerator.

Nuevo artefacto `AIArtifactType.PATIENT_SUMMARY` (docs/fase-6-rfc.md §4.3,
contrato de dominio cerrado desde el hito 6.2). Entrada: `transcript`
(siempre) y `summary_text` (texto de `SUMMARY` si esa ejecución lo produjo,
cadena vacía si no — dependencia blanda, ver `PatientSummaryStep`). Salida
en lenguaje llano dirigido al paciente, distinta del resumen técnico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True, frozen=True)
class PatientSummaryDraft:
    text: str
    #: Usage real del proveedor (Fase 6.3) — `None` en
    #: `MockPatientSummaryGenerator`. Ver `steps/base.py::ProduceResult`.
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Tokens de razonamiento facturables, separados de `output_tokens`
    #: (Google Gemini únicamente hoy) — ver
    #: `LanguageModelResponse.reasoning_tokens`.
    reasoning_tokens: int | None = None


class PatientSummaryGenerator(Protocol):
    async def generate(
        self, transcript: str, summary_text: str, *, context: SessionContext
    ) -> PatientSummaryDraft: ...
