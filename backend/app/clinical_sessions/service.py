"""ClinicalSessionService: autoriza → valida transición → opera → audita → commit.

Cada método sigue el mismo patrón transaccional que PatientService: la
escritura de la entidad y su entrada de auditoría se confirman con un
único commit; si cualquiera de las dos falla, ambas se revierten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_sessions.domain import state_machine
from app.clinical_sessions.domain.entities import (
    CREATABLE_STATUSES,
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)
from app.clinical_sessions.domain.normalization import normalize_free_text
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.core.authorization import ClinicalSessionAction, authorize_clinical_session_action
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository


@dataclass(slots=True)
class ClinicalSessionCreateData:
    patient_id: uuid.UUID
    professional_id: uuid.UUID
    session_type: SessionType
    status: ClinicalSessionStatus
    scheduled_at: datetime | None
    title: str | None
    administrative_notes: str | None


@dataclass(slots=True)
class ClinicalSessionUpdateData:
    """Solo los campos presentes en `provided` se consideran para el update."""

    provided: dict[str, Any]


class ClinicalSessionService:
    def __init__(
        self,
        session: AsyncSession,
        clinical_session_repository: SqlAlchemyClinicalSessionRepository | None = None,
        patient_repository: SqlAlchemyPatientRepository | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._sessions = clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._users = user_repository or SqlAlchemyUserRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    # --- Creación, lectura, listado -----------------------------------

    async def create(
        self, current_user: CurrentUser, data: ClinicalSessionCreateData, request_id: str
    ) -> ClinicalSession:
        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.CREATE, professional_id=data.professional_id
        )

        if data.status not in CREATABLE_STATUSES:
            raise ConflictError(
                f"'{data.status.value}' no es un estado inicial válido para crear una sesión."
            )

        await self._validate_patient(current_user, data.patient_id)
        await self._validate_professional(current_user, data.professional_id)

        now = datetime.now(UTC)
        started_at = (
            now
            if data.status in (ClinicalSessionStatus.IN_PROGRESS, ClinicalSessionStatus.COMPLETED)
            else None
        )
        ended_at = now if data.status == ClinicalSessionStatus.COMPLETED else None

        new_session = ClinicalSession(
            id=uuid.uuid4(),
            clinic_id=current_user.clinic_id,
            patient_id=data.patient_id,
            professional_id=data.professional_id,
            session_type=data.session_type,
            status=data.status,
            scheduled_at=data.scheduled_at,
            started_at=started_at,
            ended_at=ended_at,
            title=normalize_free_text(data.title) if data.title else data.title,
            administrative_notes=(
                normalize_free_text(data.administrative_notes)
                if data.administrative_notes
                else data.administrative_notes
            ),
            reviewed_by=None,
            reviewed_at=None,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=now,  # provisional; se sustituye por el valor real de la BD
            updated_at=now,
            schema_version=1,
            is_archived=False,
            archived_at=None,
        )

        try:
            persisted = await self._sessions.add(self._session, new_session)
            await self._write_audit(
                current_user,
                request_id,
                action="clinical_session.created",
                entity_id=persisted.id,
                metadata={"initial_status": persisted.status.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return persisted

    async def get(self, current_user: CurrentUser, session_id: uuid.UUID) -> ClinicalSession:
        authorize_clinical_session_action(current_user, ClinicalSessionAction.READ)
        return await self._get_or_404(current_user, session_id)

    async def list(
        self,
        current_user: CurrentUser,
        *,
        patient_id: uuid.UUID | None,
        professional_id: uuid.UUID | None,
        status: ClinicalSessionStatus | None,
        session_type: SessionType | None,
        scheduled_from: date | None,
        scheduled_to: date | None,
        search: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[ClinicalSession], int]:
        authorize_clinical_session_action(current_user, ClinicalSessionAction.READ)
        return await self._sessions.list(
            self._session,
            current_user.clinic_id,
            patient_id=patient_id,
            professional_id=professional_id,
            status=status,
            session_type=session_type,
            scheduled_from=scheduled_from,
            scheduled_to=scheduled_to,
            search=search,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )

    async def list_eligible_professionals(self, current_user: CurrentUser) -> list[User]:
        """Usuarios de la clínica de `current_user` que pueden ser
        `professional_id` de una sesión clínica — misma regla que
        `_validate_professional` (activo, rol `admin`/`audiologist`),
        expuesta como lectura para poblar el selector del formulario.
        `ClinicalSessionAction.READ`, no `CREATE`: a diferencia de crear
        una sesión, `viewer` sí puede ver este listado (igual que puede
        ver `list`/`get`) — `CREATE` además exige propiedad
        (`professional_id == current_user.id` para `audiologist`, ver
        `authorize_clinical_session_action`), una restricción que no
        aplica a un simple listado de candidatos."""
        authorize_clinical_session_action(current_user, ClinicalSessionAction.READ)
        return await self._users.list_eligible_professionals(self._session, current_user.clinic_id)

    # --- Edición de metadatos y profesional -----------------------------

    async def update(
        self,
        current_user: CurrentUser,
        session_id: uuid.UUID,
        data: ClinicalSessionUpdateData,
        request_id: str,
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)

        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.UPDATE, professional_id=existing.professional_id
        )

        provided_fields = set(data.provided.keys())
        changing_professional = "professional_id" in provided_fields
        if changing_professional:
            authorize_clinical_session_action(
                current_user,
                ClinicalSessionAction.CHANGE_PROFESSIONAL,
                professional_id=existing.professional_id,
            )

        state_machine.validate_editable_fields(
            existing.status, existing.is_archived, provided_fields
        )

        values: dict[str, Any] = {}
        changed_fields: list[str] = []
        previous_professional_id: uuid.UUID | None = None
        new_professional_id: uuid.UUID | None = None

        for field_name in ("title", "administrative_notes"):
            if field_name in data.provided:
                raw = data.provided[field_name]
                new_value = normalize_free_text(raw) if raw else raw
                if new_value != getattr(existing, field_name):
                    values[field_name] = new_value
                    changed_fields.append(field_name)

        if "session_type" in data.provided:
            new_value = data.provided["session_type"]
            if new_value != existing.session_type:
                values["session_type"] = new_value
                changed_fields.append("session_type")

        if "scheduled_at" in data.provided:
            new_value = data.provided["scheduled_at"]
            if new_value != existing.scheduled_at:
                values["scheduled_at"] = new_value
                changed_fields.append("scheduled_at")

        if changing_professional:
            requested = data.provided["professional_id"]
            if requested != existing.professional_id:
                await self._validate_professional(current_user, requested)
                previous_professional_id = existing.professional_id
                new_professional_id = requested
                values["professional_id"] = requested

        if not changed_fields and new_professional_id is None:
            return existing

        values["updated_by"] = current_user.id
        values["updated_at"] = datetime.now(UTC)

        try:
            updated = await self._sessions.update_fields(
                self._session, current_user.clinic_id, existing.id, values
            )
            assert updated is not None  # ya verificado por _get_or_404
            if changed_fields:
                await self._write_audit(
                    current_user,
                    request_id,
                    action="clinical_session.updated",
                    entity_id=existing.id,
                    metadata={"changed_fields": changed_fields},
                )
            if new_professional_id is not None:
                await self._write_audit(
                    current_user,
                    request_id,
                    action="clinical_session.professional_changed",
                    entity_id=existing.id,
                    metadata={
                        "previous_professional_id": str(previous_professional_id),
                        "new_professional_id": str(new_professional_id),
                    },
                )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    # --- Transiciones de estado -----------------------------------------

    async def start(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        return await self._transition(
            current_user,
            session_id,
            request_id,
            action=ClinicalSessionAction.START,
            transition_key="start",
            date_field="started_at",
        )

    async def complete(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        return await self._transition(
            current_user,
            session_id,
            request_id,
            action=ClinicalSessionAction.COMPLETE,
            transition_key="complete",
            date_field="ended_at",
        )

    async def submit_review(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        return await self._transition(
            current_user,
            session_id,
            request_id,
            action=ClinicalSessionAction.SUBMIT_REVIEW,
            transition_key="submit_review",
            date_field=None,
        )

    async def review(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)
        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.REVIEW, professional_id=existing.professional_id
        )
        if existing.is_archived:
            raise ConflictError("No se puede transicionar una sesión archivada.")

        new_status = state_machine.resolve_transition("review", existing.status)
        if new_status is None:
            return existing  # no-op idempotente: no reescribe reviewed_by/reviewed_at

        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "status": new_status.value,
            "updated_by": current_user.id,
            "updated_at": now,
        }
        if existing.reviewed_by is None:
            values["reviewed_by"] = current_user.id
        if existing.reviewed_at is None:
            values["reviewed_at"] = now

        try:
            updated = await self._sessions.update_fields(
                self._session, current_user.clinic_id, existing.id, values
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action="clinical_session.status_changed",
                entity_id=existing.id,
                metadata={"from_status": existing.status.value, "to_status": new_status.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def cancel(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)
        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.CANCEL, professional_id=existing.professional_id
        )
        if existing.is_archived:
            raise ConflictError("No se puede transicionar una sesión archivada.")

        new_status = state_machine.resolve_transition("cancel", existing.status)
        if new_status is None:
            return existing

        try:
            updated = await self._sessions.update_fields(
                self._session,
                current_user.clinic_id,
                existing.id,
                {
                    "status": new_status.value,
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action="clinical_session.cancelled",
                entity_id=existing.id,
                metadata={"from_status": existing.status.value, "to_status": new_status.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    # --- Archivado / restauración ---------------------------------------

    async def archive(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)
        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.ARCHIVE, professional_id=existing.professional_id
        )

        if not state_machine.resolve_archive(existing.status, existing.is_archived):
            return existing  # idempotente: ya archivada, no-op

        try:
            updated = await self._sessions.update_fields(
                self._session,
                current_user.clinic_id,
                existing.id,
                {
                    "is_archived": True,
                    "archived_at": datetime.now(UTC),
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user, request_id, action="clinical_session.archived", entity_id=existing.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def restore(
        self, current_user: CurrentUser, session_id: uuid.UUID, request_id: str
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)
        authorize_clinical_session_action(
            current_user, ClinicalSessionAction.RESTORE, professional_id=existing.professional_id
        )

        if not state_machine.resolve_restore(existing.is_archived):
            return existing  # idempotente: ya activa, no-op

        try:
            updated = await self._sessions.update_fields(
                self._session,
                current_user.clinic_id,
                existing.id,
                {
                    "is_archived": False,
                    "archived_at": None,
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user, request_id, action="clinical_session.restored", entity_id=existing.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    # --- Helpers internos -------------------------------------------------

    async def _transition(
        self,
        current_user: CurrentUser,
        session_id: uuid.UUID,
        request_id: str,
        *,
        action: ClinicalSessionAction,
        transition_key: str,
        date_field: str | None,
    ) -> ClinicalSession:
        existing = await self._get_or_404(current_user, session_id)
        authorize_clinical_session_action(
            current_user, action, professional_id=existing.professional_id
        )
        if existing.is_archived:
            raise ConflictError("No se puede transicionar una sesión archivada.")

        new_status = state_machine.resolve_transition(transition_key, existing.status)
        if new_status is None:
            return existing  # no-op idempotente

        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "status": new_status.value,
            "updated_by": current_user.id,
            "updated_at": now,
        }
        if date_field is not None and getattr(existing, date_field) is None:
            values[date_field] = now

        try:
            updated = await self._sessions.update_fields(
                self._session, current_user.clinic_id, existing.id, values
            )
            assert updated is not None
            await self._write_audit(
                current_user,
                request_id,
                action="clinical_session.status_changed",
                entity_id=existing.id,
                metadata={"from_status": existing.status.value, "to_status": new_status.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def _get_or_404(
        self, current_user: CurrentUser, session_id: uuid.UUID
    ) -> ClinicalSession:
        clinical_session = await self._sessions.get_by_id(
            self._session, current_user.clinic_id, session_id
        )
        if clinical_session is None:
            raise NotFoundError("Sesión clínica no encontrada.")
        return clinical_session

    async def _validate_patient(self, current_user: CurrentUser, patient_id: uuid.UUID) -> None:
        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")
        if patient.is_archived:
            raise ConflictError("No se puede crear una sesión para un paciente archivado.")

    async def _validate_professional(
        self, current_user: CurrentUser, professional_id: uuid.UUID
    ) -> None:
        professional = await self._users.get_by_id(self._session, professional_id)
        if professional is None or professional.clinic_id != current_user.clinic_id:
            raise NotFoundError("Profesional no encontrado.")
        if not professional.is_active:
            raise ConflictError("El profesional responsable debe estar activo.")
        if professional.role not in (Role.ADMIN, Role.AUDIOLOGIST):
            raise ConflictError("El profesional responsable debe tener rol admin o audiologist.")

    async def _write_audit(
        self,
        current_user: CurrentUser,
        request_id: str,
        *,
        action: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._audit.add(
            self._session,
            AuditLogEntry(
                id=uuid.uuid4(),
                clinic_id=current_user.clinic_id,
                actor_user_id=current_user.id,
                action=action,
                entity_type="clinical_session",
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
            ),
        )
