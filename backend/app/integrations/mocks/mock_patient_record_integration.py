"""MockPatientRecordIntegration: determinista, sin I/O de red.

Misma entrada -> misma salida (ver docs/architecture.md §4) — mismo
criterio de test que el resto de `Mock*` del proyecto (Fase 4.4). Sin
caller todavía: contrato + mock probado, ver docs/development-plan.md
Fase 7.3.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from app.integrations.domain.patient_record_integration import (
    PatientRecordFetchResult,
    PatientRecordSyncInput,
    PatientRecordSyncResult,
)

_FIXED_SYNCED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_FIXED_DATE_OF_BIRTH = date(1970, 1, 1)


def _fake_external_reference_id(patient_id: str) -> str:
    return f"noah-{hashlib.sha256(patient_id.encode()).hexdigest()[:12]}"


class MockPatientRecordIntegration:
    async def sync_patient(self, input: PatientRecordSyncInput) -> PatientRecordSyncResult:
        return PatientRecordSyncResult(
            external_reference_id=(
                input.external_reference_id or _fake_external_reference_id(str(input.patient_id))
            ),
            synced_at=_FIXED_SYNCED_AT,
            status="synced",
        )

    async def fetch_patient(self, external_reference_id: str) -> PatientRecordFetchResult | None:
        if not external_reference_id.startswith("noah-"):
            return None
        return PatientRecordFetchResult(
            external_reference_id=external_reference_id,
            first_name="Paciente",
            last_name="Ficticio",
            date_of_birth=_FIXED_DATE_OF_BIRTH,
        )
