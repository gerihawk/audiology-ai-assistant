"""Puerto del repositorio de consentimientos.

El dominio y el servicio solo conocen esta interfaz; la implementación
concreta con SQLAlchemy vive en infrastructure/repository.py.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.consents.domain.entities import Consent, ConsentType


class ConsentRepository(Protocol):
    async def add(self, session: AsyncSession, consent: Consent) -> Consent: ...

    async def get_latest(
        self,
        session: AsyncSession,
        clinic_id: uuid.UUID,
        patient_id: uuid.UUID,
        consent_type: ConsentType,
    ) -> Consent | None:
        """El registro más reciente (`recorded_at` descendente) para ese
        paciente y tipo de consentimiento, o `None` si nunca se registró
        ninguno. Un `granted=false` posterior revoca uno anterior sin
        borrar el histórico — se comprueba siempre el más reciente."""
        ...

    async def list_by_patient(
        self, session: AsyncSession, clinic_id: uuid.UUID, patient_id: uuid.UUID
    ) -> list[Consent]:
        """Histórico completo (todos los tipos), `recorded_at` descendente
        — Fase 7.1. Nunca oculta registros revocados: el histórico es
        append-only (ver `get_latest`)."""
        ...
