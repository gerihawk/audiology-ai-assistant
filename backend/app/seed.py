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
from datetime import UTC, datetime, timedelta

from app.clinical_sessions.domain.entities import (
    ClinicalSession,
    ClinicalSessionStatus,
    SessionType,
)
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
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


def _dev_sessions(
    clinic_id: uuid.UUID,
    patient_ids_by_code: dict[str, uuid.UUID],
    admin_id: uuid.UUID,
    audiologist_id: uuid.UUID,
) -> tuple[ClinicalSession, ...]:
    """Sesiones clínicas ficticias de ejemplo, en distintos estados.

    Construidas directamente como entidades de dominio (igual que el resto
    del seed): no pasan por `ClinicalSessionService`, así que no generan
    entradas de `audit_logs` — coherente con el resto del seed, que
    tampoco audita la creación de la clínica/usuarios/pacientes.
    """
    now = _now()
    session_started_1_day_ago = now - timedelta(days=1, minutes=30)
    session_ended_1_day_ago = now - timedelta(days=1)
    return (
        ClinicalSession(
            id=uuid.uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_ids_by_code["PAT-0001"],
            professional_id=admin_id,
            session_type=SessionType.INITIAL_ASSESSMENT,
            status=ClinicalSessionStatus.SCHEDULED,
            scheduled_at=now + timedelta(days=7),
            started_at=None,
            ended_at=None,
            title="Primera visita programada",
            administrative_notes="Paciente deriva de revisión rutinaria.",
            reviewed_by=None,
            reviewed_at=None,
            created_by=admin_id,
            updated_by=admin_id,
            created_at=now,
            updated_at=now,
            schema_version=1,
            is_archived=False,
            archived_at=None,
        ),
        ClinicalSession(
            id=uuid.uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_ids_by_code["PAT-0001"],
            professional_id=audiologist_id,
            session_type=SessionType.FOLLOW_UP,
            status=ClinicalSessionStatus.IN_PROGRESS,
            scheduled_at=now,
            started_at=now,
            ended_at=None,
            title="Seguimiento en curso",
            administrative_notes=None,
            reviewed_by=None,
            reviewed_at=None,
            created_by=audiologist_id,
            updated_by=audiologist_id,
            created_at=now,
            updated_at=now,
            schema_version=1,
            is_archived=False,
            archived_at=None,
        ),
        ClinicalSession(
            id=uuid.uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_ids_by_code["PAT-0002"],
            professional_id=audiologist_id,
            session_type=SessionType.HEARING_AID_FITTING,
            status=ClinicalSessionStatus.COMPLETED,
            scheduled_at=session_ended_1_day_ago,
            started_at=session_started_1_day_ago,
            ended_at=session_ended_1_day_ago,
            title="Adaptación de audífonos completada",
            administrative_notes="Pendiente de enviar a revisión.",
            reviewed_by=None,
            reviewed_at=None,
            created_by=audiologist_id,
            updated_by=audiologist_id,
            created_at=now,
            updated_at=now,
            schema_version=1,
            is_archived=False,
            archived_at=None,
        ),
    )


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
    clinical_session_repository = SqlAlchemyClinicalSessionRepository()

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
        patient_ids_by_code: dict[str, uuid.UUID] = {}
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
                patient_ids_by_code[spec["internal_code"]] = patient.id
                print(f"[creado]     paciente {spec['internal_code']}")
            else:
                patient_ids_by_code[spec["internal_code"]] = existing_patient.id
                print(f"[existente]  paciente {spec['internal_code']}")

        audiologist_id = user_ids_by_role[Role.AUDIOLOGIST]
        for spec in _dev_sessions(clinic.id, patient_ids_by_code, admin_id, audiologist_id):
            existing_matches, _ = await clinical_session_repository.list(
                session,
                clinic.id,
                patient_id=spec.patient_id,
                professional_id=None,
                status=None,
                session_type=None,
                scheduled_from=None,
                scheduled_to=None,
                search=spec.title,
                include_archived=True,
                limit=1,
                offset=0,
            )
            if existing_matches:
                print(f"[existente]  sesión clínica {spec.title!r}")
                continue
            await clinical_session_repository.add(session, spec)
            await session.commit()
            print(f"[creada]     sesión clínica {spec.title!r} ({spec.status.value})")

    print("\nSeed completado. Cabecera de desarrollo para probar la API:")
    for role, user_id in user_ids_by_role.items():
        print(f"  X-Dev-User-Id: {user_id}   ({role.value})")


if __name__ == "__main__":
    asyncio.run(run_seed())
