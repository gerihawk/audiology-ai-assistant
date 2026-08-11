"""Precondición del hito 6.0 (docs/fase-6-rfc.md §9.1): el permiso de
exportación existe y se aplica antes de que exista el servicio de
exportación (hito 6.6)."""

from __future__ import annotations

import uuid

import pytest

from app.core.authorization import ClinicalDocumentAction, authorize_clinical_document_action
from app.core.current_user import CurrentUser
from app.core.exceptions import ForbiddenError
from app.users.domain.entities import Role


def _user(role: Role) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(), clinic_id=uuid.uuid4(), email="x@example.com", display_name="X", role=role
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.AUDIOLOGIST])
def test_admin_and_audiologist_can_export(role: Role):
    authorize_clinical_document_action(_user(role), ClinicalDocumentAction.EXPORT)


def test_viewer_cannot_export():
    with pytest.raises(ForbiddenError):
        authorize_clinical_document_action(_user(Role.VIEWER), ClinicalDocumentAction.EXPORT)
