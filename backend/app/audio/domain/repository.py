"""Puerto del repositorio de grabaciones de audio.

Sin `clinic_id` propio en `audio_recordings` (ver entities.py): cada
método exige `clinic_id` igualmente, resuelto internamente mediante un
join contra `clinical_sessions` — mismo principio de "aislamiento
estructural por clínica" que el resto del proyecto (ver
docs/architecture.md §10), aplicado a través de la sesión clínica dueña
del audio en vez de una columna directa.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.domain.entities import AudioRecording


class AudioRecordingRepository(Protocol):
    async def add(
        self, session: AsyncSession, audio_recording: AudioRecording
    ) -> AudioRecording: ...

    async def get_by_id(
        self, session: AsyncSession, clinic_id: uuid.UUID, audio_recording_id: uuid.UUID
    ) -> AudioRecording | None: ...

    async def list_by_session(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> list[AudioRecording]: ...

    async def get_latest_transcribable(
        self, session: AsyncSession, clinic_id: uuid.UUID, clinical_session_id: uuid.UUID
    ) -> AudioRecording | None:
        """El audio más reciente de la sesión en estado `ready` o
        `transcribed` (candidato a transcribir/re-transcribir). `None` si
        no hay ninguno en ese estado."""
        ...

    async def update_fields(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        audio_recording_id: uuid.UUID,
        values: dict[str, Any],
    ) -> AudioRecording | None: ...

    async def list_expired(
        self, session: AsyncSession, clinic_id: uuid.UUID, cutoff: datetime
    ) -> list[AudioRecording]:
        """Grabaciones con `status != deleted` y `uploaded_at < cutoff` —
        incluye deliberadamente estados atascados (`failed`/`uploaded`/
        `validating`/`transcribing`), no solo `ready`/`transcribed` (Fase
        7.2). Ordenado por `uploaded_at` ascendente: lo más vencido
        primero, al revés que el resto de listados de audio."""
        ...
