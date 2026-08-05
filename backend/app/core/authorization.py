"""Autorización centralizada.

Ningún router ni repositorio implementa comprobaciones de rol propias:
todo pasa por las funciones `authorize_*` definidas aquí.
"""

from __future__ import annotations

import uuid
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


class ClinicalSessionAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    CHANGE_PROFESSIONAL = "change_professional"
    START = "start"
    COMPLETE = "complete"
    SUBMIT_REVIEW = "submit_review"
    REVIEW = "review"
    CANCEL = "cancel"
    ARCHIVE = "archive"
    RESTORE = "restore"


CLINICAL_SESSION_PERMISSIONS: dict[Role, frozenset[ClinicalSessionAction]] = {
    Role.ADMIN: frozenset(ClinicalSessionAction),
    Role.AUDIOLOGIST: frozenset(
        {
            ClinicalSessionAction.CREATE,
            ClinicalSessionAction.READ,
            ClinicalSessionAction.UPDATE,
            ClinicalSessionAction.START,
            ClinicalSessionAction.COMPLETE,
            ClinicalSessionAction.SUBMIT_REVIEW,
            ClinicalSessionAction.CANCEL,
            ClinicalSessionAction.ARCHIVE,
        }
    ),
    Role.VIEWER: frozenset({ClinicalSessionAction.READ}),
}

#: Acciones para las que, siendo `audiologist`, se exige además ser el
#: profesional responsable de la sesión (`professional_id ==
#: current_user.id`) — "sus propias sesiones", nunca las de un compañero
#: de la misma clínica. `admin` no tiene esta restricción.
_OWNERSHIP_REQUIRED_ACTIONS: frozenset[ClinicalSessionAction] = frozenset(
    {
        ClinicalSessionAction.UPDATE,
        ClinicalSessionAction.START,
        ClinicalSessionAction.COMPLETE,
        ClinicalSessionAction.SUBMIT_REVIEW,
        ClinicalSessionAction.CANCEL,
        ClinicalSessionAction.ARCHIVE,
    }
)


def authorize_clinical_session_action(
    current_user: CurrentUser,
    action: ClinicalSessionAction,
    *,
    professional_id: uuid.UUID | None = None,
) -> None:
    """Autoriza una acción sobre `clinical_sessions`.

    `professional_id` es el `professional_id` de la sesión ya existente
    sobre la que se actúa (`None` para acciones sin sesión concreta, p.
    ej. `CREATE` o el listado). Para `audiologist`, las acciones en
    `_OWNERSHIP_REQUIRED_ACTIONS` exigen además que
    `professional_id == current_user.id` — la comprobación de propiedad
    de la sesión, no solo de rol.
    """
    if action not in CLINICAL_SESSION_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre sesiones clínicas."
        )
    if (
        current_user.role == Role.AUDIOLOGIST
        and action in _OWNERSHIP_REQUIRED_ACTIONS
        and professional_id != current_user.id
    ):
        raise ForbiddenError(
            "Un audiologist solo puede operar sobre sus propias sesiones clínicas."
        )
