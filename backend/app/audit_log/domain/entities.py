"""Entidad de dominio AuditLogEntry. Sin dependencias de SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AuditLogEntry:
    id: uuid.UUID
    clinic_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    request_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None
