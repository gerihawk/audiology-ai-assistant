"""Autorización centralizada.

Ningún router ni repositorio implementa comprobaciones de rol propias:
todo pasa por las funciones `authorize_*` definidas aquí.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.current_user import CurrentUser
from app.core.exceptions import ForbiddenError
from app.users.domain.entities import Role


class PatientAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    ARCHIVE = "archive"
    RESTORE = "restore"


PATIENT_PERMISSIONS: dict[Role, frozenset[PatientAction]] = {
    Role.ADMIN: frozenset(PatientAction),
    Role.AUDIOLOGIST: frozenset(
        {
            PatientAction.CREATE,
            PatientAction.READ,
            PatientAction.UPDATE,
            PatientAction.ARCHIVE,
        }
    ),
    Role.VIEWER: frozenset({PatientAction.READ}),
}


def authorize_patient_action(current_user: CurrentUser, action: PatientAction) -> None:
    if action not in PATIENT_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre pacientes."
        )
