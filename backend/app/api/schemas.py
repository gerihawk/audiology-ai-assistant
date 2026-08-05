"""Esquemas de las rutas de apoyo (/me, /dev/users) — no ligadas a un módulo de negocio."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.users.domain.entities import Role


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    email: str
    display_name: str
    role: Role


class DevUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    display_name: str
    role: Role
