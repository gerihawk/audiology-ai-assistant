"""Entidades de dominio del onboarding self-service (Fase 12). Sin
dependencias de SQLAlchemy.

`AccountToken` (hito 12.1): token de un solo uso para dos propósitos,
ambos ligados a un `User` ya existente en `users`: verificación del email
de registro (el admin creado por `POST /clinics/signup` empieza
`is_active=False`) y recuperación de contraseña.

`Invitation` (hito 12.2): decisión tomada — tabla propia, NO una extensión
de `AccountToken`. Un `AccountToken` está atado a un `user_id` NOT NULL
(el usuario ya existe); una invitación describe un email que TODAVÍA no
tiene `User` y necesita, además, `clinic_id` y el `role` propuesto — forzar
esto en `account_tokens` habría exigido hacer `user_id` nullable y añadir
columnas irrelevantes para verificación/reseteo. Ver docs/fase-12-rfc.md
§4.2/§5.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.users.domain.entities import Role


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


#: Roles que un admin puede proponer al invitar a un compañero — nunca
#: `admin` desde este flujo, para evitar que cualquier invitación acabe
#: creando otro administrador de la clínica sin pasar por una decisión
#: explícita fuera de este endpoint (ver docs/fase-12-rfc.md §4.2).
INVITABLE_ROLES: frozenset[Role] = frozenset({Role.AUDIOLOGIST, Role.VIEWER})


@dataclass(slots=True)
class Invitation:
    id: uuid.UUID
    clinic_id: uuid.UUID
    #: Normalizado (recortado + minúsculas, ver
    #: app.onboarding.domain.normalization.normalize_email) — igual que
    #: `User.email`, pero aquí SIN unicidad propia: `invalidate_pending`
    #: permite reinvitar el mismo email tantas veces como haga falta,
    #: solo el último enlace enviado es válido.
    email: str
    role: Role
    #: SHA-256 hex digest — mismo criterio que `AccountToken.token_hash`.
    token_hash: str
    expires_at: datetime
    #: `None` mientras está pendiente. Se fija también (a "ahora") para
    #: invalidar una invitación pendiente que nunca se aceptó de verdad —
    #: mismo truco que `AccountToken.used_at`/`invalidate_pending` (ver
    #: app/onboarding/infrastructure/repository.py).
    accepted_at: datetime | None
    #: El admin que envió la invitación — trazabilidad, sin uso en la
    #: lógica de aceptación.
    created_by: uuid.UUID
    created_at: datetime

    @property
    def is_usable(self) -> bool:
        """Mismo criterio que `AccountToken.is_usable`."""
        if self.accepted_at is not None:
            return False
        return datetime.now(UTC) < self.expires_at
