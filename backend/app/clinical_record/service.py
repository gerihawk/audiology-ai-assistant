"""ClinicalRecordService: autoriza → resuelve página longitudinal → audita
→ commit — Hito 6.7.3 (docs/fase-6-rfc.md §7.5/§8).

Servicio de solo lectura clínica: la única escritura es el evento de
auditoría `clinical_record.viewed`. Mismo patrón transaccional que
`ExportService`/`PatientService` — la construcción de la página (que puede
fallar: ninguna de las llamadas de resolución está envuelta en `try`)
sucede ANTES de escribir cualquier fila, así que un fallo nunca deja una
auditoría de vista exitosa a medias.

Reutiliza exclusivamente repositorios públicos ya existentes de otros
módulos (`PatientRepository`, `ClinicalSessionRepository`,
`AIArtifactRepository`) y las primitivas puras de dominio de
`clinical_record` (hito 6.7.1) — nunca `AIPipelineService.list_artifacts()`
(reautorizaría/resolvería cada sesión por su cuenta) ni el ORM de esos
módulos directamente. `clinical_record` no tiene ORM, tabla ni migración
propia (RFC §3.4/§8, Decisión cerrada 15).
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_record.domain.entities import (
    ClinicalRecordPage,
    ClinicalRecordPatientRef,
    LoadedSessionArtifacts,
    build_clinical_record_page,
    is_eligible_artifact,
)
from app.clinical_sessions.domain.entities import ClinicalSession
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.core.authorization import ClinicalRecordAction, authorize_clinical_record_action
from app.core.current_user import CurrentUser
from app.core.exceptions import NotFoundError
from app.patients.domain.repository import PatientRepository
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository

__all__ = ["ClinicalRecordService"]


def _apply_known_anamnesis_baseline(
    page: ClinicalRecordPage, current_baseline_artifact_id: uuid.UUID | None
) -> ClinicalRecordPage:
    """`build_clinical_record_page` (6.7.1) decide `is_current_baseline`
    cruzando únicamente las sesiones de ESTA página
    (`find_current_anamnesis_baseline` solo ve `sessions`, el argumento
    recibido) — correcto si la página contiene la ANAMNESIS vigente de
    todo el paciente, pero potencialmente una marca clínicamente falsa si
    la vigente real vive en otra página (encargo 6.7.3: "no queremos una
    marca longitudinal falsa por efecto de la paginación").

    Se recalcula aquí con la identidad ya resuelta una única vez, sobre el
    paciente completo, por `AIArtifactRepository.get_latest_approved` —
    sin ninguna consulta adicional ni reimplementar la selección
    (`approved_at DESC` + desempate por `id` sigue viviendo exclusivamente
    en esa consulta): cualquier `ANAMNESIS` de la página que no sea
    exactamente ese artefacto queda en `False`, esté o no la vigente real
    dentro de esta página."""
    return replace(
        page,
        sessions=tuple(
            replace(
                entry,
                documents=tuple(
                    replace(
                        doc,
                        is_current_baseline=(
                            doc.artifact_type == AIArtifactType.ANAMNESIS
                            and current_baseline_artifact_id is not None
                            and doc.ai_artifact_id == current_baseline_artifact_id
                        ),
                    )
                    for doc in entry.documents
                ),
            )
            for entry in page.sessions
        ),
    )


class ClinicalRecordService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        patient_repository: PatientRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        artifact_repository: AIArtifactRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._artifacts = artifact_repository or SqlAlchemyAIArtifactRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def get_record(
        self,
        current_user: CurrentUser,
        patient_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        request_id: str,
    ) -> ClinicalRecordPage:
        authorize_clinical_record_action(current_user, ClinicalRecordAction.READ)

        # Aislamiento de clínica primero, mismo `NotFoundError` para
        # "no existe" y "es de otra clínica" (app/core/exceptions.py):
        # nunca se filtra cuál de los dos casos ocurrió.
        patient = await self._patients.get_by_id(self._session, current_user.clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")

        # Unidad de paginación: sesiones, no documentos (encargo 6.7.3).
        # `include_archived=True`: el expediente longitudinal es la
        # historia completa del paciente — archivar una sesión es un
        # estado administrativo (igual que archivar un paciente), no una
        # eliminación de contenido clínico.
        sessions, total = await self._clinical_sessions.list(
            self._session,
            current_user.clinic_id,
            patient_id=patient_id,
            professional_id=None,
            status=None,
            session_type=None,
            scheduled_from=None,
            scheduled_to=None,
            search=None,
            include_archived=True,
            limit=limit,
            offset=offset,
        )

        # Resuelto UNA vez sobre el paciente completo, nunca por página
        # (ver `_apply_known_anamnesis_baseline`). `exclude_clinical_session_id`
        # se deja en su default `None`: aquí no hay "sesión actual" que
        # excluir, a diferencia de `AIPipelineService._resolve_patient_context`.
        current_baseline = await self._artifacts.get_latest_approved(
            self._session, current_user.clinic_id, patient_id, AIArtifactType.ANAMNESIS
        )
        current_baseline_id = current_baseline.id if current_baseline is not None else None

        loaded_sessions = [
            await self._load_session_artifacts(current_user.clinic_id, clinical_session)
            for clinical_session in sessions
        ]

        page = build_clinical_record_page(
            patient=ClinicalRecordPatientRef(
                patient_id=patient.id,
                internal_code=patient.internal_code,
                display_name=patient.display_name,
            ),
            sessions=loaded_sessions,
            total=total,
            limit=limit,
            offset=offset,
        )
        page = _apply_known_anamnesis_baseline(page, current_baseline_id)

        try:
            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="clinical_record.viewed",
                    entity_type="patient",
                    entity_id=patient_id,
                    request_id=request_id,
                    metadata={
                        "patient_id": str(patient_id),
                        "limit": limit,
                        "offset": offset,
                        "sessions_returned": len(page.sessions),
                    },
                ),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return page

    async def _load_session_artifacts(
        self, clinic_id: uuid.UUID, clinical_session: ClinicalSession
    ) -> LoadedSessionArtifacts:
        artifacts = await self._artifacts.list_by_session(
            self._session, clinic_id, clinical_session.id
        )
        loaded_pairs = []
        for artifact in artifacts:
            if not is_eligible_artifact(artifact):
                continue
            assert artifact.current_version_id is not None  # invariante: status == APPROVED
            version = await self._artifacts.get_version_by_id(
                self._session, artifact.current_version_id
            )
            assert version is not None  # invariante: current_version_id ya resuelto
            loaded_pairs.append((artifact, version))
        return LoadedSessionArtifacts(
            clinical_session_id=clinical_session.id,
            session_type=clinical_session.session_type.value,
            created_at=clinical_session.created_at,
            artifacts=tuple(loaded_pairs),
        )
