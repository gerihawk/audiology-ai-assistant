"""Tests de integración de `ClinicalRecordService` — Hito 6.7.3
(docs/fase-6-rfc.md §7.5/§8), contra base de datos real de test.

Construye `AIArtifact`/`AIArtifactVersion` directamente vía
`SqlAlchemyAIArtifactRepository` (mismo patrón que
`test_ai_pipeline_artifact_repository.py::_approve_anamnesis`/
`_leave_pending`), sin pasar por `AIPipelineService` ni por endpoints —
6.7.3 no incluye API todavía. No duplica los tests de dominio puro de
6.7.1 (`test_clinical_record_domain.py`): solo demuestra que el wiring
real desde BD (autorización, aislamiento de clínica, paginación,
resolución del baseline de ANAMNESIS vigente y auditoría) es correcto.

`session_type=None` no se ejercita aquí: `ClinicalSessionORM.session_type`
es `NOT NULL` en el esquema real (ver `app.export.domain.entities.
ExportableDocument`, mismo caso) — ese caso ya está cubierto en
`test_clinical_record_domain.py` con un `LoadedSessionArtifacts`
construido a mano."""

from __future__ import annotations

import uuid
from dataclasses import fields
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
    AIArtifactVersionSource,
)
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.audit_log.infrastructure.orm import AuditLogORM
from app.clinical_record.service import ClinicalRecordService
from app.clinical_sessions.domain.entities import ClinicalSession
from app.core.exceptions import NotFoundError
from app.patients.domain.entities import Patient
from app.users.domain.entities import Role
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    create_clinical_session,
    create_patient,
    current_user_from,
)

_ARTIFACT_REPO = SqlAlchemyAIArtifactRepository()


async def _create_artifact(
    session: AsyncSession,
    clinical_session: ClinicalSession,
    *,
    artifact_type: AIArtifactType,
    status: AIArtifactStatus = AIArtifactStatus.APPROVED,
    approved_by: uuid.UUID | None = None,
    approved_at: datetime | None = None,
    content: dict | None = None,
) -> AIArtifact:
    """Crea un `AIArtifact` con el `status` pedido. Solo `APPROVED` recibe
    una versión (`current_version_id` resuelto) — `review_pending`/
    `rejected` se quedan sin versión, igual que
    `test_ai_pipeline_artifact_repository.py::_leave_pending`: nunca
    llegan a ser elegibles, así que `ClinicalRecordService` nunca intenta
    resolver su versión."""
    artifact_id = uuid.uuid4()
    now = approved_at or datetime.now(UTC)
    inserted = await _ARTIFACT_REPO.insert_new(
        session,
        AIArtifact(
            id=artifact_id,
            clinical_session_id=clinical_session.id,
            artifact_type=artifact_type,
            status=AIArtifactStatus.REVIEW_PENDING,
            current_version_id=None,
            confidence=None,
            schema_version=1,
            approved_by=None,
            approved_at=None,
            rejected_by=None,
            rejected_at=None,
            rejection_reason=None,
            deleted_by=None,
            deleted_at=None,
            created_at=now,
            updated_at=now,
        ),
    )
    if status == AIArtifactStatus.REVIEW_PENDING:
        await session.commit()
        return inserted

    if status == AIArtifactStatus.REJECTED:
        updated = await _ARTIFACT_REPO.update_disposition(
            session,
            clinical_session.clinic_id,
            artifact_id,
            {
                "status": AIArtifactStatus.REJECTED.value,
                "rejected_by": approved_by,
                "rejected_at": now,
                "rejection_reason": "Motivo de prueba, sin contenido clínico real.",
                "updated_at": now,
            },
        )
        await session.commit()
        assert updated is not None
        return updated

    version = await _ARTIFACT_REPO.insert_version(
        session,
        AIArtifactVersion(
            id=uuid.uuid4(),
            ai_artifact_id=artifact_id,
            version_number=1,
            content=(
                content if content is not None else {"text": f"contenido {artifact_type.value}"}
            ),
            confidence=80,
            source_map={"text": "map interno, nunca debe salir del DTO"},
            source=AIArtifactVersionSource.AI_GENERATED,
            generation_run_id=None,
            created_by=None,
            change_note=None,
            created_at=now,
        ),
    )
    updated = await _ARTIFACT_REPO.update_disposition(
        session,
        clinical_session.clinic_id,
        artifact_id,
        {
            "current_version_id": version.id,
            "status": AIArtifactStatus.APPROVED.value,
            "approved_by": approved_by,
            "approved_at": now,
            "updated_at": now,
        },
    )
    await session.commit()
    assert updated is not None
    return updated


async def _soft_delete(
    session: AsyncSession, clinical_session: ClinicalSession, artifact: AIArtifact, *, by: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    updated = await _ARTIFACT_REPO.update_disposition(
        session,
        clinical_session.clinic_id,
        artifact.id,
        {"deleted_by": by, "deleted_at": now, "updated_at": now},
    )
    await session.commit()
    assert updated is not None


async def _session(
    db_session: AsyncSession, clinic: ClinicWithUsers, patient_id: uuid.UUID
) -> ClinicalSession:
    return await create_clinical_session(
        db_session, clinic.clinic.id, patient_id, clinic.audiologist.id, clinic.admin.id
    )


# ============================================================
# Estructura básica de la página: sesiones, documentos, filtrado por status
# ============================================================


class TestPageStructure:
    async def test_patient_without_sessions_returns_empty_page(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-empty",
        )
        assert page.sessions == ()
        assert page.total == 0
        assert page.patient.patient_id == patient.id
        assert page.patient.internal_code == patient.internal_code

    async def test_session_without_approved_artifacts_has_empty_documents(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            status=AIArtifactStatus.REVIEW_PENDING,
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-1",
        )

        assert len(page.sessions) == 1
        assert page.sessions[0].clinical_session_id == clinical_session.id
        assert page.sessions[0].documents == ()

    async def test_only_approved_artifact_survives_mixed_statuses(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        approved = await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.CLINICAL_FLAGS,
            status=AIArtifactStatus.REVIEW_PENDING,
        )
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.MISSING_INFORMATION,
            status=AIArtifactStatus.REJECTED,
            approved_by=clinic_with_users.audiologist.id,
        )
        deleted = await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.TRANSCRIPT,
            approved_by=clinic_with_users.audiologist.id,
        )
        await _soft_delete(
            db_session, clinical_session, deleted, by=clinic_with_users.audiologist.id
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-2",
        )

        documents = page.sessions[0].documents
        assert len(documents) == 1
        assert documents[0].ai_artifact_id == approved.id
        assert documents[0].artifact_type == AIArtifactType.SUMMARY

    async def test_documents_within_session_ordered_by_pipeline_step_order(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        # Insertados deliberadamente en orden NO canónico.
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
        )
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.TRANSCRIPT,
            approved_by=clinic_with_users.audiologist.id,
        )
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-3",
        )

        types = [doc.artifact_type for doc in page.sessions[0].documents]
        assert types == [
            AIArtifactType.TRANSCRIPT,
            AIArtifactType.SUMMARY,
            AIArtifactType.ANAMNESIS,
        ]


# ============================================================
# Paginación: unidad = sesiones, total = sesiones, sin huecos ni repeticiones
# ============================================================


class TestPagination:
    async def test_multiple_sessions_returned_in_chronological_order(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        first = await _session(db_session, clinic_with_users, patient.id)
        second = await _session(db_session, clinic_with_users, patient.id)
        third = await _session(db_session, clinic_with_users, patient.id)

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-order",
        )

        assert [entry.clinical_session_id for entry in page.sessions] == [
            first.id,
            second.id,
            third.id,
        ]

    async def test_pagination_without_repeats_or_gaps(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        created = [await _session(db_session, clinic_with_users, patient.id) for _ in range(5)]

        service = ClinicalRecordService(db_session)
        current_user = current_user_from(clinic_with_users.admin)
        seen: list[uuid.UUID] = []
        for offset in (0, 2, 4):
            page = await service.get_record(
                current_user, patient.id, limit=2, offset=offset, request_id=f"req-page-{offset}"
            )
            assert page.total == 5
            seen.extend(entry.clinical_session_id for entry in page.sessions)

        assert seen == [s.id for s in created]
        assert len(set(seen)) == 5

    async def test_total_counts_sessions_not_documents(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        for _ in range(2):
            clinical_session = await _session(db_session, clinic_with_users, patient.id)
            for artifact_type in (
                AIArtifactType.TRANSCRIPT,
                AIArtifactType.SUMMARY,
                AIArtifactType.CLINICAL_FLAGS,
            ):
                await _create_artifact(
                    db_session,
                    clinical_session,
                    artifact_type=artifact_type,
                    approved_by=clinic_with_users.audiologist.id,
                )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-total",
        )
        assert page.total == 2


# ============================================================
# Aislamiento de clínica
# ============================================================


class TestTenantIsolation:
    async def test_patient_from_other_clinic_returns_not_found(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        other_clinic = await create_clinic_with_users(db_session)
        other_patient = await create_patient(
            db_session, other_clinic.clinic.id, other_clinic.admin.id
        )

        service = ClinicalRecordService(db_session)
        with pytest.raises(NotFoundError):
            await service.get_record(
                current_user_from(clinic_with_users.admin),
                other_patient.id,
                limit=20,
                offset=0,
                request_id="req-404",
            )

    async def test_other_clinic_sessions_and_artifacts_never_leak(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        own_session = await _session(db_session, clinic_with_users, patient.id)
        await _create_artifact(
            db_session,
            own_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        other_clinic = await create_clinic_with_users(db_session)
        other_patient = await create_patient(
            db_session, other_clinic.clinic.id, other_clinic.admin.id
        )
        other_session = await create_clinical_session(
            db_session,
            other_clinic.clinic.id,
            other_patient.id,
            other_clinic.audiologist.id,
            other_clinic.admin.id,
        )
        await _create_artifact(
            db_session,
            other_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=other_clinic.audiologist.id,
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-isolation",
        )

        assert page.total == 1
        assert [entry.clinical_session_id for entry in page.sessions] == [own_session.id]


# ============================================================
# Autorización end-to-end (wiring, no la matriz completa — ver
# test_clinical_record_authorization.py)
# ============================================================


class TestAuthorizationWiring:
    @pytest.mark.parametrize("role_attr", ["admin", "audiologist", "viewer"])
    async def test_all_three_roles_can_read(
        self,
        db_session: AsyncSession,
        clinic_with_users: ClinicWithUsers,
        patient: Patient,
        role_attr: str,
    ):
        user = getattr(clinic_with_users, role_attr)
        assert user.role in (Role.ADMIN, Role.AUDIOLOGIST, Role.VIEWER)
        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(user), patient.id, limit=20, offset=0, request_id="req-role"
        )
        assert page.total == 0


# ============================================================
# ANAMNESIS vigente independiente de la paginación
# ============================================================


class TestCurrentAnamnesisBaseline:
    async def test_two_historical_anamnesis_both_visible_only_latest_is_baseline(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        older_session = await _session(db_session, clinic_with_users, patient.id)
        newer_session = await _session(db_session, clinic_with_users, patient.id)
        older = await _create_artifact(
            db_session,
            older_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        newer = await _create_artifact(
            db_session,
            newer_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-baseline",
        )

        by_artifact_id = {
            doc.ai_artifact_id: doc for entry in page.sessions for doc in entry.documents
        }
        assert set(by_artifact_id) == {older.id, newer.id}
        assert by_artifact_id[older.id].is_current_baseline is False
        assert by_artifact_id[newer.id].is_current_baseline is True

    async def test_baseline_outside_current_page_marks_no_historical_as_current(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        older_session = await _session(db_session, clinic_with_users, patient.id)
        newer_session = await _session(db_session, clinic_with_users, patient.id)
        await _create_artifact(
            db_session,
            older_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # La vigente real es esta (approved_at más reciente), pero vive en
        # `newer_session` — fuera de la página que pedimos abajo
        # (limit=1, offset=0 -> solo `older_session`, la primera creada).
        await _create_artifact(
            db_session,
            newer_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            approved_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=1,
            offset=0,
            request_id="req-baseline-outside",
        )

        assert len(page.sessions) == 1
        assert page.sessions[0].clinical_session_id == older_session.id
        anamnesis_docs = [
            doc
            for doc in page.sessions[0].documents
            if doc.artifact_type == AIArtifactType.ANAMNESIS
        ]
        assert len(anamnesis_docs) == 1
        assert anamnesis_docs[0].is_current_baseline is False

    async def test_session_notes_never_carries_baseline_semantics(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SESSION_NOTES,
            approved_by=clinic_with_users.audiologist.id,
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-session-notes",
        )

        documents = page.sessions[0].documents
        assert len(documents) == 1
        assert documents[0].artifact_type == AIArtifactType.SESSION_NOTES
        assert documents[0].is_current_baseline is False


# ============================================================
# Minimización de datos: sin source_excerpt/source_map/metadata interna
# ============================================================


class TestDataMinimization:
    async def test_response_never_exposes_source_excerpt_or_generation_metadata(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        content = {
            "tinnitus": {
                "value": "sí",
                "status": "informado",
                "source_excerpt": "cita textual que nunca debe salir del DTO",
            }
        }
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.ANAMNESIS,
            approved_by=clinic_with_users.audiologist.id,
            content=content,
        )

        service = ClinicalRecordService(db_session)
        page = await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-minimize",
        )

        document = page.sessions[0].documents[0]
        assert "source_excerpt" not in _flatten(document.content)
        document_field_names = {f.name for f in fields(document)}
        assert document_field_names == {
            "ai_artifact_id",
            "artifact_type",
            "version_number",
            "approved_by",
            "approved_at",
            "content",
            "is_current_baseline",
        }


def _flatten(node) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        keys.update(node.keys())
        for value in node.values():
            keys.update(_flatten(value))
    elif isinstance(node, list):
        for value in node:
            keys.update(_flatten(value))
    return keys


# ============================================================
# Auditoría: exactamente un clinical_record.viewed, metadata exacta, nunca
# antes del éxito
# ============================================================


class TestAudit:
    async def test_successful_view_writes_exactly_one_audit_event(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        service = ClinicalRecordService(db_session)
        await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-audit-1",
        )

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "clinical_record.viewed",
                AuditLogORM.entity_id == patient.id,
            )
        )
        entries = result.scalars().all()
        assert len(entries) == 1

    async def test_audit_metadata_is_exact_and_free_of_phi(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers, patient: Patient
    ):
        clinical_session = await _session(db_session, clinic_with_users, patient.id)
        await _create_artifact(
            db_session,
            clinical_session,
            artifact_type=AIArtifactType.SUMMARY,
            approved_by=clinic_with_users.audiologist.id,
        )

        service = ClinicalRecordService(db_session)
        await service.get_record(
            current_user_from(clinic_with_users.admin),
            patient.id,
            limit=20,
            offset=0,
            request_id="req-audit-2",
        )

        result = await db_session.execute(
            select(AuditLogORM).where(
                AuditLogORM.action == "clinical_record.viewed",
                AuditLogORM.entity_id == patient.id,
            )
        )
        entry = result.scalar_one()
        assert entry.actor_user_id == clinic_with_users.admin.id
        assert entry.entity_type == "patient"
        assert entry.audit_metadata == {
            "patient_id": str(patient.id),
            "limit": 20,
            "offset": 0,
            "sessions_returned": 1,
        }

    async def test_not_found_before_success_writes_no_audit_event(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        other_clinic = await create_clinic_with_users(db_session)
        other_patient = await create_patient(
            db_session, other_clinic.clinic.id, other_clinic.admin.id
        )

        service = ClinicalRecordService(db_session)
        with pytest.raises(NotFoundError):
            await service.get_record(
                current_user_from(clinic_with_users.admin),
                other_patient.id,
                limit=20,
                offset=0,
                request_id="req-audit-404",
            )

        result = await db_session.execute(
            select(AuditLogORM).where(AuditLogORM.action == "clinical_record.viewed")
        )
        assert result.scalars().all() == []
