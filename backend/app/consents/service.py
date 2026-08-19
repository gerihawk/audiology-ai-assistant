"""ConsentService: autoriza → valida paciente → determina consent_version →
persiste → audita → commit transaccional. Fase 7.1
(docs/development-plan.md) — cierra el único hueco del módulo `consents`
(dominio/infraestructura ya existían desde el hito 6.0): conceder
consentimiento no tenía ni servicio ni endpoint todavía.

Mismo patrón transaccional que `ClinicalSessionService`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.consents.domain.entities import Consent, ConsentType
from app.consents.infrastructure.repository import SqlAlchemyConsentRepository
from app.core.authorization import ConsentAction, authorize_consent_action
from app.core.config import get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository


@dataclass(slots=True)
class ConsentCreateData:
    consent_type: ConsentType
    granted: bool
    notes: str | None


def _consent_version_for(consent_type: ConsentType) -> str | None:
    """Solo `procesamiento_ia` tiene una versión de política definida hoy
    (`Settings.ai_processing_consent_version`, ya consumida por
    `AIPipelineService._ensure_ai_processing_consent`). `grabacion_audio`/
    `almacenamiento` no tienen política versionada todavía — esta fase no
    la introduce, solo refleja lo que ya existe. Siempre decidido por el
    servidor, nunca por el cliente (ver `ConsentCreateRequest`, que ni
    siquiera declara el campo)."""
    if consent_type == ConsentType.PROCESAMIENTO_IA:
        return get_settings().ai_processing_consent_version
    return None


class ConsentService:
    def __init__(
        self,
        session: AsyncSession,
        consent_repository: SqlAlchemyConsentRepository | None = None,
        patient_repository: SqlAlchemyPatientRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._consents = consent_repository or SqlAlchemyConsentRepository()
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def create(
        self,
        current_user: CurrentUser,
        patient_id: uuid.UUID,
        data: ConsentCreateData,
        request_id: str,
    ) -> Consent:
        authorize_consent_action(current_user, ConsentAction.CREATE)
        await self._validate_patient(current_user, patient_id)

        # `clinical_session_id` queda fuera de esta ronda (decisión de
        # alcance de la Fase 7.1) — el dominio ya soporta el campo para
        # cuando se necesite; aquí siempre `None` (consentimiento a nivel
        # paciente). `recorded_at=None`: lo fija `server_default` en el
        # INSERT, nunca el cliente ni el servicio.
        new_consent = Consent(
            id=uuid.uuid4(),
            clinic_id=current_user.clinic_id,
            patient_id=patient_id,
            clinical_session_id=None,
            consent_type=data.consent_type,
            granted=data.granted,
            consent_version=_consent_version_for(data.consent_type),
            granted_by=current_user.id,
            recorded_at=None,
            notes=data.notes,
        )

        try:
            # Histórico append-only por diseño (ver
            # `ConsentRepository.get_latest`): siempre un INSERT nuevo,
            # nunca un UPDATE sobre un registro anterior.
            persisted = await self._consents.add(self._session, new_consent)
            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="consent.registered",
                    entity_type="consent",
                    entity_id=persisted.id,
                    request_id=request_id,
                    metadata={
                        "consent_type": persisted.consent_type.value,
                        "granted": persisted.granted,
                        "consent_version": persisted.consent_version,
                    },
                ),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return persisted

    async def list_by_patient(
        self, current_user: CurrentUser, patient_id: uuid.UUID
    ) -> list[Consent]:
        authorize_consent_action(current_user, ConsentAction.READ)
        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")
        return await self._consents.list_by_patient(
            self._session, current_user.clinic_id, patient_id
        )

    async def _validate_patient(self, current_user: CurrentUser, patient_id: uuid.UUID) -> None:
        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")
        if patient.is_archived:
            raise ConflictError(
                "No se puede registrar un consentimiento para un paciente archivado."
            )
