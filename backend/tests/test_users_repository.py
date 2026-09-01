"""`SqlAlchemyUserRepository.list_eligible_professionals` — misma regla que
`ClinicalSessionService._validate_professional`: activo, rol
admin/audiologist, misma clínica."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.users.domain.entities import Role
from app.users.infrastructure.repository import SqlAlchemyUserRepository
from tests.factories import ClinicWithUsers, create_clinic, create_user


async def test_incluye_admin_y_audiologist_activos_de_la_misma_clinica(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    result = await SqlAlchemyUserRepository().list_eligible_professionals(
        db_session, clinic_with_users.clinic.id
    )

    ids = {user.id for user in result}
    assert clinic_with_users.admin.id in ids
    assert clinic_with_users.audiologist.id in ids


async def test_excluye_viewer(db_session: AsyncSession, clinic_with_users: ClinicWithUsers) -> None:
    result = await SqlAlchemyUserRepository().list_eligible_professionals(
        db_session, clinic_with_users.clinic.id
    )

    ids = {user.id for user in result}
    assert clinic_with_users.viewer.id not in ids


async def test_excluye_usuarios_inactivos(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    inactive_admin = await create_user(
        db_session, clinic_with_users.clinic.id, role=Role.ADMIN, is_active=False
    )

    result = await SqlAlchemyUserRepository().list_eligible_professionals(
        db_session, clinic_with_users.clinic.id
    )

    ids = {user.id for user in result}
    assert inactive_admin.id not in ids
    assert clinic_with_users.admin.id in ids


async def test_excluye_usuarios_de_otra_clinica(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    other_clinic = await create_clinic(db_session)
    other_admin = await create_user(db_session, other_clinic.id, role=Role.ADMIN)

    result = await SqlAlchemyUserRepository().list_eligible_professionals(
        db_session, clinic_with_users.clinic.id
    )

    ids = {user.id for user in result}
    assert other_admin.id not in ids


async def test_orden_alfabetico_por_display_name(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers
) -> None:
    clinic = await create_clinic(db_session)
    await create_user(db_session, clinic.id, role=Role.ADMIN, display_name="Zulema Admin")
    await create_user(db_session, clinic.id, role=Role.AUDIOLOGIST, display_name="Ana Audio")

    result = await SqlAlchemyUserRepository().list_eligible_professionals(db_session, clinic.id)

    assert [user.display_name for user in result] == ["Ana Audio", "Zulema Admin"]
