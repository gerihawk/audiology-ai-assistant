"""ClinicalRecordService: autoriza → resuelve página longitudinal → audita
→ commit — Hito 6.7.3 (docs/fase-6-rfc.md §7.5/§8). Hito 6.7.4 añade
`export_record()`: autoriza (doble) → resuelve la MISMA ventana
longitudinal que `get_record()` → construye `ExportBundle` → renderiza →
audita `document.exported` (scope="patient") → commit.

Servicio de solo lectura clínica: las únicas escrituras son los eventos de
auditoría `clinical_record.viewed`/`document.exported`. Mismo patrón
transaccional que `ExportService`/`PatientService` — toda construcción que
puede fallar (resolución de datos, renderizado) sucede ANTES de escribir
cualquier fila, así que un fallo nunca deja una auditoría a medias.

Reutiliza exclusivamente repositorios públicos ya existentes de otros
módulos (`PatientRepository`, `ClinicalSessionRepository`,
`AIArtifactRepository`, `SqlAlchemyClinicRepository`) y las primitivas
puras de dominio de `clinical_record` (hito 6.7.1) y `export.domain`
(`build_exportable_document`, hito 6.6.1) — nunca
`AIPipelineService.list_artifacts()` ni `ExportService` (reautorizarían/
resolverían por su cuenta) ni el ORM de esos módulos directamente.
`clinical_record` no tiene ORM, tabla ni migración propia (RFC §3.4/§8,
Decisión cerrada 15).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.entities import PIPELINE_STEP_ORDER, AIArtifactType
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
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.authorization import (
    ClinicalDocumentAction,
    ClinicalRecordAction,
    authorize_clinical_document_action,
    authorize_clinical_record_action,
)
from app.core.config import get_settings
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.export.domain.entities import (
    ExportableDocument,
    ExportBundle,
    ExportBundleSession,
    build_exportable_document,
)
from app.export.domain.exporter import DocumentExporter
from app.export.infrastructure.pdf_exporter import PdfDocumentExporter
from app.export.infrastructure.text_exporter import TextDocumentExporter
from app.patients.domain.entities import Patient
from app.patients.domain.repository import PatientRepository
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository

__all__ = ["ExportFormat", "ClinicalRecordExportResult", "ClinicalRecordService"]

#: `Literal` (no `StrEnum`) por el mismo motivo que `export.service.
#: ExportFormat`: FastAPI valida el query param `format` de forma nativa
#: (422 ante un valor desconocido) sin código de validación propio. Se
#: redefine aquí en vez de importarse de `export.service` para no acoplar
#: este módulo al servicio de exportación individual (módulo hermano, no
#: dependencia — ver docstring de arriba).
ExportFormat = Literal["pdf", "text"]

_MEDIA_TYPE_BY_FORMAT: dict[ExportFormat, str] = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
}
_EXTENSION_BY_FORMAT: dict[ExportFormat, str] = {"pdf": "pdf", "text": "txt"}

#: Misma whitelist que `export.service._UNSAFE_FILENAME_CHARS` (duplicada,
#: no importada: `export.service` no forma parte del alcance de 6.7.4,
#: encargo "no cambios en 6.6"). Solo alfanumérico, guion y guion bajo —
#: impide header injection y path traversal en `Content-Disposition`.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def _build_longitudinal_filename(
    *, patient_internal_code: str, generated_at: datetime, export_format: ExportFormat
) -> str:
    """ASCII-safe, determinista, a partir de `internal_code` — nunca
    `display_name` (texto clínico libre)."""
    safe_code = _UNSAFE_FILENAME_CHARS.sub("_", patient_internal_code).strip("_") or "paciente"
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    extension = _EXTENSION_BY_FORMAT[export_format]
    return f"{safe_code}_historia_clinica_{timestamp}.{extension}"


@dataclass(slots=True, frozen=True)
class ClinicalRecordExportResult:
    content: bytes
    media_type: str
    filename: str


def _build_export_documents(
    loaded_session: LoadedSessionArtifacts,
    *,
    clinic_name: str,
    patient: Patient,
    generated_at: datetime,
) -> tuple[ExportableDocument, ...]:
    """Filtra por elegibilidad y ordena por `PIPELINE_STEP_ORDER` los
    pares `(AIArtifact, AIArtifactVersion)` ya cargados de una sesión, y
    construye cada `ExportableDocument` vía `build_exportable_document`
    (hito 6.6.1) — nunca reimplementa saneado de `source_excerpt`, hash ni
    metadata del documento. No reutiliza `sort_documents_by_pipeline_order`
    (hito 6.7.1: opera sobre `ClinicalRecordDocument`, no sobre pares
    `(AIArtifact, AIArtifactVersion)`) — mismo índice de orden, aplicado
    aquí directamente sobre los pares crudos."""
    order_index = {artifact_type: i for i, artifact_type in enumerate(PIPELINE_STEP_ORDER)}
    eligible_pairs = sorted(
        (pair for pair in loaded_session.artifacts if is_eligible_artifact(pair[0])),
        key=lambda pair: order_index[pair[0].artifact_type],
    )
    return tuple(
        build_exportable_document(
            clinic_name=clinic_name,
            patient_internal_code=patient.internal_code,
            patient_display_name=patient.display_name,
            clinical_session_id=loaded_session.clinical_session_id,
            session_type=loaded_session.session_type,
            artifact=artifact,
            version=version,
            generated_at=generated_at,
        )
        for artifact, version in eligible_pairs
    )


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
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        text_exporter: DocumentExporter | None = None,
        pdf_exporter: DocumentExporter | None = None,
    ) -> None:
        self._session = session
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._artifacts = artifact_repository or SqlAlchemyAIArtifactRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._text_exporter = text_exporter or TextDocumentExporter()
        self._pdf_exporter = pdf_exporter or PdfDocumentExporter()

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
        patient = await self._get_patient(current_user.clinic_id, patient_id)

        loaded_sessions, total = await self._load_session_window(
            current_user.clinic_id, patient_id, limit=limit, offset=offset
        )

        # Resuelto UNA vez sobre el paciente completo, nunca por página
        # (ver `_apply_known_anamnesis_baseline`). `exclude_clinical_session_id`
        # se deja en su default `None`: aquí no hay "sesión actual" que
        # excluir, a diferencia de `AIPipelineService._resolve_patient_context`.
        current_baseline = await self._artifacts.get_latest_approved(
            self._session, current_user.clinic_id, patient_id, AIArtifactType.ANAMNESIS
        )
        current_baseline_id = current_baseline.id if current_baseline is not None else None

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

    async def export_record(
        self,
        current_user: CurrentUser,
        patient_id: uuid.UUID,
        *,
        export_format: ExportFormat,
        limit: int | None,
        offset: int,
        request_id: str,
    ) -> ClinicalRecordExportResult:
        # Orden cerrado (encargo 6.7.4): READ antes que EXPORT antes que
        # tocar la BD — nunca se filtra si el paciente existe a un rol sin
        # ningún permiso sobre `clinical_record`.
        authorize_clinical_record_action(current_user, ClinicalRecordAction.READ)
        authorize_clinical_document_action(current_user, ClinicalDocumentAction.EXPORT)
        patient = await self._get_patient(current_user.clinic_id, patient_id)

        # Única regla de guardarraíl (encargo 6.7.4): `effective_limit <=
        # clinical_record_export_max_sessions`, sin excepción según venga
        # o no `limit` explícito. `limit` explícito por encima del máximo
        # se rechaza aquí (409) en vez de en el schema/router: acceder a
        # `Settings` desde ahí para fijar el límite superior de `Query`
        # sería artificioso (valor fijado en tiempo de import, no de
        # petición) — encargo 6.7.4, elección documentada.
        max_sessions = get_settings().clinical_record_export_max_sessions
        if limit is not None and limit > max_sessions:
            raise ConflictError(
                "limit no puede superar el máximo exportable de "
                f"{max_sessions} sesiones; segmente la exportación con offset."
            )
        effective_limit = limit if limit is not None else max_sessions

        # Misma ventana longitudinal que `get_record()` (mismo universo de
        # sesiones/artefactos elegibles, encargo 6.7.4: "no una consulta
        # paralela con reglas distintas"), acotada a `effective_limit` —
        # nunca se cargan más de `max_sessions` filas ni en el camino que
        # termina rechazando por exceso.
        loaded_sessions, total = await self._load_session_window(
            current_user.clinic_id, patient_id, limit=effective_limit, offset=offset
        )
        if limit is None and total > max_sessions:
            raise ConflictError(
                "El paciente tiene más sesiones que el máximo exportable en una sola "
                "petición; use limit/offset para segmentar la exportación."
            )

        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        assert clinic is not None  # invariante: current_user pertenece a una clínica existente

        generated_at = datetime.now(UTC)
        bundle_sessions = tuple(
            ExportBundleSession(
                clinical_session_id=loaded.clinical_session_id,
                session_type=loaded.session_type,
                created_at=loaded.created_at,
                documents=_build_export_documents(
                    loaded, clinic_name=clinic.name, patient=patient, generated_at=generated_at
                ),
            )
            for loaded in loaded_sessions
        )

        # Vista vacía es válida (200); exportación vacía no lo es —
        # nunca un PDF/TXT vacío como descarga clínica (encargo 6.7.4).
        if not any(s.documents for s in bundle_sessions):
            raise ConflictError(
                "No hay documentos aprobados en la ventana solicitada para exportar."
            )

        bundle = ExportBundle(
            clinic_name=clinic.name,
            patient_internal_code=patient.internal_code,
            patient_display_name=patient.display_name,
            sessions=bundle_sessions,
        )

        exporter = self._pdf_exporter if export_format == "pdf" else self._text_exporter
        # Si `export_many()` lanza, termina aquí: ni auditoría ni commit
        # se ejecutan (mismo contrato que `ExportService.export`).
        content = exporter.export_many(bundle)

        filename = _build_longitudinal_filename(
            patient_internal_code=patient.internal_code,
            generated_at=generated_at,
            export_format=export_format,
        )

        try:
            await self._audit.add(
                self._session,
                AuditLogEntry(
                    id=uuid.uuid4(),
                    clinic_id=current_user.clinic_id,
                    actor_user_id=current_user.id,
                    action="document.exported",
                    entity_type="patient",
                    entity_id=patient_id,
                    request_id=request_id,
                    metadata={
                        "scope": "patient",
                        "patient_id": str(patient_id),
                        "format": export_format,
                        "limit": limit,
                        "offset": offset,
                        "sessions_included": len(bundle_sessions),
                    },
                ),
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return ClinicalRecordExportResult(
            content=content,
            media_type=_MEDIA_TYPE_BY_FORMAT[export_format],
            filename=filename,
        )

    async def _get_patient(self, clinic_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
        # Aislamiento de clínica primero, mismo `NotFoundError` para
        # "no existe" y "es de otra clínica" (app/core/exceptions.py):
        # nunca se filtra cuál de los dos casos ocurrió.
        patient = await self._patients.get_by_id(self._session, clinic_id, patient_id)
        if patient is None:
            raise NotFoundError("Paciente no encontrado.")
        return patient

    async def _load_session_window(
        self, clinic_id: uuid.UUID, patient_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[LoadedSessionArtifacts], int]:
        """Ventana de sesiones + artefactos elegibles compartida por
        `get_record()` y `export_record()` (encargo 6.7.4: "mismo universo
        de sesiones y artefactos que la vista"). Unidad de paginación:
        sesiones, no documentos. `include_archived=True`: el expediente
        longitudinal es la historia completa del paciente — archivar una
        sesión es un estado administrativo, no una eliminación de
        contenido clínico."""
        sessions, total = await self._clinical_sessions.list(
            self._session,
            clinic_id,
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
        loaded_sessions = [
            await self._load_session_artifacts(clinic_id, clinical_session)
            for clinical_session in sessions
        ]
        return loaded_sessions, total

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
