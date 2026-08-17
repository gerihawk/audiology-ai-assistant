"""Matriz de permisos de `clinical_record:read` — Hito 6.7.3
(docs/fase-6-rfc.md §7.5/§8). Deliberadamente más permisiva que
`ClinicalDocumentAction.EXPORT` (test_clinical_document_authorization.py):
`viewer` puede consultar la historia clínica longitudinal, no solo
`admin`/`audiologist`.

Los tres roles existentes (`admin`, `audiologist`, `viewer`) tienen el
permiso `clinical_record:read` — no existe ningún rol del sistema sin él,
así que no hay un caso "403 por falta de permiso" que construir sin
inventar un rol nuevo (encargo 6.7.3: "no inventes roles nuevos")."""

from __future__ import annotations

import uuid

import pytest

from app.core.authorization import ClinicalRecordAction, authorize_clinical_record_action
from app.core.current_user import CurrentUser
from app.users.domain.entities import Role


def _user(role: Role) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(), clinic_id=uuid.uuid4(), email="x@example.com", display_name="X", role=role
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.AUDIOLOGIST, Role.VIEWER])
def test_admin_audiologist_and_viewer_can_read_clinical_record(role: Role):
    authorize_clinical_record_action(_user(role), ClinicalRecordAction.READ)
