"""PatientService: autoriza → opera → audita → commit.

Cada método sigue el mismo patrón transaccional: la escritura de la
entidad y su entrada de auditoría se confirman con un único commit; si
cualquiera de las dos falla, ambas se revierten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.core.authorization import PatientAction, authorize_patient_action
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.patients.domain.entities import Patient, Sex
from app.patients.domain.normalization import normalize_free_text, normalize_internal_code
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository


@dataclass(slots=True)
class PatientCreateData:
    internal_code: str
    display_name: str | None
    birth_year: int | None
    sex: Sex | None
    preferred_language: str
    notes: str | None


@dataclass(slots=True)
class PatientUpdateData:
    """Solo los campos presentes en `provided` se consideran para el update.

    Distingue "campo omitido" (no tocar) de "campo enviado como null"
    (limpiar el valor), replicando la semántica habitual de un PATCH.
    """

    provided: dict[str, Any]


class PatientService:
    def __init__(
        self,
        session: AsyncSession,
        patient_repository: SqlAlchemyPatientRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def create(
        self, current_user: CurrentUser, data: PatientCreateData, request_id: str
    ) -> Patient:
        authorize_patient_action(current_user, PatientAction.CREATE)

        normalized_code = normalize_internal_code(data.internal_code)
        existing = await self._patients.get_by_internal_code(
            self._session, current_user.clinic_id, normalized_code
        )
        if existing is not None:
            raise ConflictError(
                "Ya existe un paciente con ese código interno en esta clínica.",
                field="internal_code",
            )

        new_patient = Patient(
            id=uuid.uuid4(),
            clinic_id=current_user.clinic_id,
            internal_code=normalized_code,
            display_name=(
                normalize_free_text(data.display_name) if data.display_name else data.display_name
            ),
            birth_year=data.birth_year,
            sex=data.sex,
            preferred_language=data.preferred_language,
            notes=normalize_free_text(data.notes) if data.notes else data.notes,
            is_archived=False,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=datetime.now(UTC),  # provisional; se sustituye por el valor real de la BD
            updated_at=datetime.now(UTC),
            archived_at=None,
            schema_version=1,
        )

        try:
            persisted = await self._patients.add(self._session, new_patient)
            await self._write_audit(
                current_user, request_id, action="patient.created", entity_id=persisted.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return persisted

    async def get(self, current_user: CurrentUser, patient_id: uuid.UUID) -> Patient:
        authorize_patient_action(current_user, PatientAction.READ)
        return await self._get_or_404(current_user, patient_id)

    async def list(
        self,
        current_user: CurrentUser,
        *,
        search: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Patient], int]:
        authorize_patient_action(current_user, PatientAction.READ)
        return await self._patients.list(
            self._session,
            current_user.clinic_id,
            search=search,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        current_user: CurrentUser,
        patient_id: uuid.UUID,
        data: PatientUpdateData,
        request_id: str,
    ) -> Patient:
        authorize_patient_action(current_user, PatientAction.UPDATE)
        patient = await self._get_or_404(current_user, patient_id)

        if patient.is_archived:
            raise ConflictError("No se puede editar un paciente archivado. Restáuralo primero.")

        values: dict[str, Any] = {}
        changed_fields: list[str] = []

        if "internal_code" in data.provided:
            normalized = normalize_internal_code(data.provided["internal_code"])
            if normalized != patient.internal_code:
                duplicate = await self._patients.get_by_internal_code(
                    self._session,
                    current_user.clinic_id,
                    normalized,
                    exclude_id=patient.id,
                )
                if duplicate is not None:
                    raise ConflictError(
                        "Ya existe un paciente con ese código interno en esta clínica.",
                        field="internal_code",
                    )
                values["internal_code"] = normalized
                changed_fields.append("internal_code")

        for field_name in ("display_name", "notes"):
            if field_name in data.provided:
                raw = data.provided[field_name]
                new_value = normalize_free_text(raw) if raw else raw
                if new_value != getattr(patient, field_name):
                    values[field_name] = new_value
                    changed_fields.append(field_name)

        for field_name in ("birth_year", "preferred_language"):
            if field_name in data.provided:
                new_value = data.provided[field_name]
                if new_value != getattr(patient, field_name):
                    values[field_name] = new_value
                    changed_fields.append(field_name)

        if "sex" in data.provided:
            new_sex = data.provided["sex"]
            if new_sex != patient.sex:
                values["sex"] = new_sex
                changed_fields.append("sex")

        if not changed_fields:
            return patient

        values["updated_by"] = current_user.id
        values["updated_at"] = datetime.now(UTC)

        try:
            updated = await self._patients.update_fields(
                self._session, current_user.clinic_id, patient.id, values
            )
            assert updated is not None  # ya verificado por _get_or_404
            await self._write_audit(
                current_user,
                request_id,
                action="patient.updated",
                entity_id=patient.id,
                metadata={"changed_fields": changed_fields},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def archive(
        self, current_user: CurrentUser, patient_id: uuid.UUID, request_id: str
    ) -> Patient:
        authorize_patient_action(current_user, PatientAction.ARCHIVE)
        patient = await self._get_or_404(current_user, patient_id)

        if patient.is_archived:
            return patient  # idempotente: ya archivado, no-op

        try:
            updated = await self._patients.update_fields(
                self._session,
                current_user.clinic_id,
                patient.id,
                {
                    "is_archived": True,
                    "archived_at": datetime.now(UTC),
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user, request_id, action="patient.archived", entity_id=patient.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def restore(
        self, current_user: CurrentUser, patient_id: uuid.UUID, request_id: str
    ) -> Patient:
        authorize_patient_action(current_user, PatientAction.RESTORE)
        patient = await self._get_or_404(current_user, patient_id)

        if not patient.is_archived:
            return patient  # idempotente: ya activo, no-op

        try:
            updated = await self._patients.update_fields(
                self._session,
                current_user.clinic_id,
                patient.id,
                {
                    "is_archived": False,
                    "archived_at": None,
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(UTC),
                },
            )
            assert updated is not None
            await self._write_audit(
                current_user, request_id, action="patient.restored", entity_id=patient.id
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return updated

    async def _get_or_404(self, current_user: CurrentUser, patient_id: uuid.UUID) -> Patient:
        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")
        return patient

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
                entity_type="patient",
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
            ),
        )
