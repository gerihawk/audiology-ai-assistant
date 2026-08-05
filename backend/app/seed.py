"""Seed de desarrollo: clínica, tres usuarios y varios pacientes ficticios.

Idempotente: si ya existen (localizados por code/email/internal_code), no
se duplican. Se niega a ejecutarse si ENVIRONMENT=production.

Uso:
    docker compose run --rm backend python -m app.seed
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core import orm_registry  # noqa: F401  (registra los modelos ORM)
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.patients.domain.entities import Patient, Sex
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository
from app.users.domain.entities import Role, User
from app.users.infrastructure.repository import SqlAlchemyUserRepository

DEV_CLINIC_CODE = "DEV-CLINIC"
DEV_CLINIC_NAME = "Clínica de Desarrollo (ficticia)"

DEV_USERS = (
    {"email": "admin@dev.local", "display_name": "Admin Ficticio", "role": Role.ADMIN},
    {
        "email": "audiologist@dev.local",
        "display_name": "Audioprotesista Ficticio",
        "role": Role.AUDIOLOGIST,
    },
    {"email": "viewer@dev.local", "display_name": "Observador Ficticio", "role": Role.VIEWER},
)

DEV_PATIENTS = (
    {
        "internal_code": "PAT-0001",
        "display_name": "Paciente Ficticio Uno",
        "birth_year": 1958,
        "sex": Sex.FEMALE,
    },
    {
        "internal_code": "PAT-0002",
        "display_name": "Paciente Ficticio Dos",
        "birth_year": 1972,
        "sex": Sex.MALE,
    },
    {
        "internal_code": "PAT-0003",
        "display_name": None,
        "birth_year": None,
        "sex": Sex.UNSPECIFIED,
    },
)


def _now() -> datetime:
    """Marca de tiempo provisional para construir la entidad antes de
    insertarla; el valor real lo fija PostgreSQL (server_default)."""
    return datetime.now(UTC)


async def run_seed() -> None:
    settings = get_settings()
    if settings.is_production:
        print(
            "El seed de desarrollo no puede ejecutarse con ENVIRONMENT=production.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    session_factory = get_session_factory()
    clinic_repository = SqlAlchemyClinicRepository()
    user_repository = SqlAlchemyUserRepository()
    patient_repository = SqlAlchemyPatientRepository()

    async with session_factory() as session:
        clinic = await clinic_repository.get_by_code(session, DEV_CLINIC_CODE)
        if clinic is None:
            clinic = Clinic(
                id=uuid.uuid4(),
                name=DEV_CLINIC_NAME,
                code=DEV_CLINIC_CODE,
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            await clinic_repository.add(session, clinic)
            await session.commit()
            print(f"[creada]     clínica {DEV_CLINIC_CODE} ({clinic.id})")
        else:
            print(f"[existente]  clínica {DEV_CLINIC_CODE} ({clinic.id})")

        user_ids_by_role: dict[Role, uuid.UUID] = {}
        for spec in DEV_USERS:
            existing_user = await user_repository.get_by_email(session, spec["email"])
            if existing_user is None:
                user = User(
                    id=uuid.uuid4(),
                    clinic_id=clinic.id,
                    email=spec["email"],
                    display_name=spec["display_name"],
                    role=spec["role"],
                    is_active=True,
                    created_at=_now(),
                    updated_at=_now(),
                )
                await user_repository.add(session, user)
                await session.commit()
                user_ids_by_role[spec["role"]] = user.id
                print(f"[creado]     usuario {spec['email']} ({spec['role'].value}) — {user.id}")
            else:
                user_ids_by_role[spec["role"]] = existing_user.id
                print(
                    f"[existente]  usuario {spec['email']} "
                    f"({existing_user.role.value}) — {existing_user.id}"
                )

        admin_id = user_ids_by_role[Role.ADMIN]
        for spec in DEV_PATIENTS:
            existing_patient = await patient_repository.get_by_internal_code(
                session, clinic.id, spec["internal_code"]
            )
            if existing_patient is None:
                patient = Patient(
                    id=uuid.uuid4(),
                    clinic_id=clinic.id,
                    internal_code=spec["internal_code"],
                    display_name=spec["display_name"],
                    birth_year=spec["birth_year"],
                    sex=spec["sex"],
                    preferred_language="es",
                    notes=None,
                    is_archived=False,
                    created_by=admin_id,
                    updated_by=admin_id,
                    created_at=_now(),
                    updated_at=_now(),
                    archived_at=None,
                    schema_version=1,
                )
                await patient_repository.add(session, patient)
                await session.commit()
                print(f"[creado]     paciente {spec['internal_code']}")
            else:
                print(f"[existente]  paciente {spec['internal_code']}")

    print("\nSeed completado. Cabecera de desarrollo para probar la API:")
    for role, user_id in user_ids_by_role.items():
        print(f"  X-Dev-User-Id: {user_id}   ({role.value})")


if __name__ == "__main__":
    asyncio.run(run_seed())
