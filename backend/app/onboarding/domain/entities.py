"""Entidad de dominio AccountToken (Fase 12, hito 12.1). Sin dependencias
de SQLAlchemy.

Token de un solo uso para dos propósitos, ambos ligados a un `User` ya
existente en `users`: verificación del email de registro (el admin creado
por `POST /clinics/signup` empieza `is_active=False`) y recuperación de
contraseña. La Fase 12, hito 12.2 (invitar a un compañero) necesitará un
token análogo para un email que TODAVÍA no tiene `User` — se decidirá
entonces si reutiliza esta misma tabla (con `user_id` nullable) o una
tabla `invitations` propia; no se amplía aquí para no diseñar por
adelantado un requisito no confirmado (mismo criterio que
docs/fase-12-rfc.md §1.2, "no objetivos").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AccountTokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


@dataclass(slots=True)
class AccountToken:
    id: uuid.UUID
    user_id: uuid.UUID
    purpose: AccountTokenPurpose
    #: SHA-256 hex digest del token en claro enviado por email — nunca se
    #: persiste el token en claro (ver
    #: app/onboarding/infrastructure/orm.py).
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime

    @property
    def is_usable(self) -> bool:
        """`False` si ya se consumió o si ha caducado — comprobado en
        Python contra `datetime.now(UTC)`, no delegado a una consulta SQL
        (mismo criterio que el resto de máquinas de estado del proyecto,
        p. ej. `ClinicalSessionStatus`)."""
        if self.used_at is not None:
            return False
        return datetime.now(UTC) < self.expires_at
