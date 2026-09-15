"""Modelos ORM del onboarding self-service: AccountToken (Fase 12, hito
12.1) e Invitation (hito 12.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AccountTokenORM(Base):
    __tablename__ = "account_tokens"
    __table_args__ = (Index("ix_account_tokens_user_purpose", "user_id", "purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 hex digest (64 caracteres) del token en claro enviado por
    # email — nunca se persiste el token en claro, mismo criterio que
    # `users.password_hash` nunca guarda la contraseña: una fuga de la
    # base de datos no debe permitir verificar/resetear cuentas
    # directamente. A diferencia de `password_hash` (bcrypt, pensado para
    # contraseñas de baja entropía elegidas por humanos), el token en
    # claro es aleatorio de alta entropía (`secrets.token_urlsafe(32)`,
    # ver `service.py`) — un hash rápido sin salt es apropiado y evita el
    # coste de bcrypt en cada verificación.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InvitationORM(Base):
    """Fase 12, hito 12.2 — ver
    app.onboarding.domain.entities.Invitation para la justificación de
    por qué es una tabla propia y no una extensión de `account_tokens`."""

    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitations_clinic_email", "clinic_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id"), nullable=False, index=True
    )
    # Sin FK a `users.email` (no existe tal columna única aparte del id) ni
    # a `users.id`: en el momento de invitar, ese `User` normalmente no
    # existe todavía — es precisamente lo que crea `accept`.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    # VARCHAR, no un tipo enum nativo de Postgres — mismo criterio que
    # `UserORM.role` (`native_enum=False` implícito al usar `String`).
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Mismo esquema de hashing que `AccountTokenORM.token_hash` (SHA-256
    # hex digest de un token aleatorio de alta entropía).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Análogo a `AccountTokenORM.used_at`: `None` mientras está pendiente,
    # fijado a "ahora" tanto al aceptarse de verdad como al invalidarse por
    # una reinvitación posterior (ver `invalidate_pending_for_email`).
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
