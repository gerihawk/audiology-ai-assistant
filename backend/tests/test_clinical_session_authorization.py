"""Auditoría RBAC del hito 8.1 (docs/privacy-and-security.md §13): la
comprobación de propiedad en `CREATE` vivía como un `if
current_user.role == Role.AUDIOLOGIST` ad-hoc en
`ClinicalSessionService.create`, no en `authorize_clinical_session_action`
— única excepción a "todo pasa por las funciones authorize_*" en todo el
backend. Estos tests cubren específicamente esa centralización, no toda la
matriz de `ClinicalSessionAction` (ya cubierta a nivel de API en
test_clinical_sessions_api.py).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.authorization import ClinicalSessionAction, authorize_clinical_session_action
from app.core.current_user import CurrentUser
from app.core.exceptions import ForbiddenError
from app.users.domain.entities import Role


def _user(role: Role, user_id: uuid.UUID | None = None) -> CurrentUser:
    return CurrentUser(
        id=user_id or uuid.uuid4(),
        clinic_id=uuid.uuid4(),
        email="x@example.com",
        display_name="X",
        role=role,
    )


def test_audiologist_can_create_session_assigned_to_self():
    audiologist = _user(Role.AUDIOLOGIST)
    authorize_clinical_session_action(
        audiologist, ClinicalSessionAction.CREATE, professional_id=audiologist.id
    )


def test_audiologist_cannot_create_session_assigned_to_another_professional():
    audiologist = _user(Role.AUDIOLOGIST)
    with pytest.raises(ForbiddenError):
        authorize_clinical_session_action(
            audiologist, ClinicalSessionAction.CREATE, professional_id=uuid.uuid4()
        )


def test_admin_can_create_session_assigned_to_another_professional():
    admin = _user(Role.ADMIN)
    authorize_clinical_session_action(
        admin, ClinicalSessionAction.CREATE, professional_id=uuid.uuid4()
    )


def test_viewer_cannot_create_session():
    viewer = _user(Role.VIEWER)
    with pytest.raises(ForbiddenError):
        authorize_clinical_session_action(
            viewer, ClinicalSessionAction.CREATE, professional_id=viewer.id
        )
