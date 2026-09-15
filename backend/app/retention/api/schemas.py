"""Esquemas de respuesta de /api/v1/retention que no reutilizan
`AudioRecordingListResponse` (ver router.py) — forma propia del resultado
de `app.retention.cli.main()`."""

from __future__ import annotations

from pydantic import BaseModel


class SystemPurgeResponse(BaseModel):
    """Resultado de `POST /api/v1/retention/system-purge`: nº de audios
    purgados por clínica (clave = `str(clinic_id)`) y las clínicas omitidas
    por no tener ningún admin activo — mismo par que devuelve
    `app.retention.cli.main()`."""

    purged: dict[str, int]
    omitted_clinics: list[str]
