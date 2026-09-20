"""Entidad de dominio PlatformOperator. Sin dependencias de SQLAlchemy.

Deliberadamente sin `clinic_id` ni `role`: un `PlatformOperator` no
pertenece a ninguna clínica, es la identidad de quien opera la plataforma
en sí (Fase 14). Nunca se mezcla con `app.users.domain.entities.User`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class PlatformOperator:
    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Igual que `User.password_hash`: `None` = sin contraseña asignada
    # todavía, nunca autentica con éxito (ver PlatformAdminAuthService.login).
    password_hash: str | None = None
