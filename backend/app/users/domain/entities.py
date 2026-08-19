"""Entidad de dominio User y enum Role. Sin dependencias de SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    AUDIOLOGIST = "audiologist"
    VIEWER = "viewer"


@dataclass(slots=True)
class User:
    id: uuid.UUID
    clinic_id: uuid.UUID
    email: str
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Hash bcrypt (Fase 9, hito 9.1). `None` = "sin contraseña asignada
    # todavía" (los usuarios de seed anteriores a esta fase, hasta que se
    # actualicen) — un usuario sin `password_hash` nunca autentica con
    # éxito, ver `AuthService.login`.
    password_hash: str | None = None
