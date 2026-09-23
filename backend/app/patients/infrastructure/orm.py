"""Modelo ORM de Patient."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.field_encryption import EncryptedInt, EncryptedString


class PatientORM(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("clinic_id", "internal_code", name="uq_patients_clinic_internal_code"),
        Index("ix_patients_clinic_archived", "clinic_id", "is_archived"),
        Index("ix_patients_clinic_created_at", "clinic_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id"), nullable=False, index=True
    )
    internal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Cifrados a nivel de aplicación desde 2026-09-18 (ver
    # app/core/field_encryption.py y docs/privacy-and-security.md §4) —
    # antes String(200)/Integer en claro. El límite de longitud de
    # display_name ya no lo impone esta columna (el ciphertext siempre es
    # más largo que el texto plano); la validación de negocio sigue
    # viviendo en app/patients/api/schemas.py. NUNCA filtrar/ordenar por
    # estas dos columnas en SQL (ilike, ==, etc.) — el cifrado no es
    # determinista, cualquier búsqueda debe resolverse en Python después
    # de leer la fila (ver SqlAlchemyPatientRepository.list).
    display_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    birth_year: Mapped[int | None] = mapped_column(EncryptedInt, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_language: Mapped[str] = mapped_column(
        String(5), nullable=False, default="es", server_default="es"
    )
    # Cifrado desde 2026-09-23 (hallazgo del red team, docs/security/
    # red-team-app-2026-09-22.md §B1 — antes String(2000) en claro, a
    # diferencia de display_name/birth_year de arriba). Mismo tipo, mismo
    # criterio: el límite real de longitud vive en
    # app/patients/api/schemas.py (_NOTES_MAX_LENGTH = 2000), nunca en esta
    # columna. `notes` no se usa en ningún filtro/ilike de SQL (verificado
    # en SqlAlchemyPatientRepository), así que no hereda la limitación de
    # no-determinismo de forma distinta a display_name.
    notes: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Distinta de `archived_at`: un paciente puede archivarse (reversible,
    # oculto de listados) sin que nadie haya ejercido el derecho de
    # supresión. `identity_purged_at` solo se rellena desde
    # `RetentionCleanupService.purge_patient_clinical_data()` (hallazgo
    # medio red team, docs/security/red-team-app-2026-09-22.md — cierre
    # 2026-09-23) al anonimizar `display_name`/`birth_year`/`notes`/
    # `internal_code` in-place; es irreversible y es la única forma de
    # distinguir auditablemente "archivado" de "identidad anonimizada por
    # RGPD" (ver docs/privacy-and-security.md §8.2).
    identity_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
