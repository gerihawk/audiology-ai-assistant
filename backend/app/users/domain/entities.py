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
