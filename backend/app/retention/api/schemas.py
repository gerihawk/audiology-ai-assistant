"""Esquemas de respuesta de /api/v1/retention que no reutilizan
`AudioRecordingListResponse` (ver router.py) — forma propia del resultado
de `app.retention.cli.main()`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SystemPurgeResponse(BaseModel):
    """Resultado de `POST /api/v1/retention/system-purge`: nº de audios
    purgados por clínica (clave = `str(clinic_id)`) y las clínicas omitidas
    por no tener ningún admin activo — mismo par que devuelve
    `app.retention.cli.main()`."""

    purged: dict[str, int]
    omitted_clinics: list[str]


class PatientDataPurgeRequest(BaseModel):
    """`confirm` con tipo `Literal[True]` (no `bool`): un `false` o un
    campo ausente son rechazados por Pydantic con 422 antes de llegar a
    ningún código de dominio — primera barrera contra un borrado
    irreversible disparado sin confirmación explícita (segunda barrera:
    `RetentionCleanupService.purge_patient_clinical_data`, ver
    docs/privacy-and-security.md §8)."""

    confirm: Literal[True]


class PatientDataPurgeResponse(BaseModel):
    """Resultado de `POST /api/v1/retention/patients/{patient_id}/purge`
    — nº de filas eliminadas físicamente por tabla, mismo que
    `PatientDataPurgeSummary` de `app.retention.service`."""

    clinical_sessions_purged: int
    ai_artifacts_purged: int
    audio_recordings_purged: int
