"""Modelo ORM de AccountToken (Fase 12, hito 12.1)."""

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
