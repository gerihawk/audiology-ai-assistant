"""Entidad de dominio Clinic. Sin dependencias de SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Clinic:
    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
