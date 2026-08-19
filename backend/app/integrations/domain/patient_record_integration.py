"""Puerto PatientRecordIntegration — historia clínica externa (p. ej. Noah).

PROVISIONAL: firma basada en una investigación ligera de alcance, no en la
API real de ningún proveedor concreto. Solo contrato + mock en el MVP (ver
docs/architecture.md §4) — sin llamada de red real, sin caller desde
ningún otro módulo. Cualquier integración real futura exige su propio
ciclo de análisis de alcance antes de tocarse (ver "Fuera de las fases del
MVP" en docs/development-plan.md).

DTOs propios, nunca las entidades `Patient`/`ClinicalSession` directamente
— mismo patrón que `TranscriptionInput`/`TranscriptionResult` del resto de
proveedores (ver docs/architecture.md §11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol


@dataclass(slots=True, frozen=True)
class PatientRecordSyncInput:
    patient_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    #: Presente si el paciente ya se sincronizó antes; `None` en la
    #: primera sincronización.
    external_reference_id: str | None = None


@dataclass(slots=True, frozen=True)
class PatientRecordSyncResult:
    external_reference_id: str
    synced_at: datetime
    status: Literal["synced", "failed"]


@dataclass(slots=True, frozen=True)
class PatientRecordFetchResult:
    external_reference_id: str
    first_name: str
    last_name: str
    date_of_birth: date


class PatientRecordIntegration(Protocol):
    async def sync_patient(self, input: PatientRecordSyncInput) -> PatientRecordSyncResult: ...

    async def fetch_patient(
        self, external_reference_id: str
    ) -> PatientRecordFetchResult | None: ...
