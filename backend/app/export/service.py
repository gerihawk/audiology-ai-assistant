"""ExportService: autoriza → resuelve artefacto/versión vigente → construye
`ExportableDocument` (6.6.1) → renderiza (6.6.2/6.6.3) → audita → commit —
Hito 6.6.4 (docs/fase-6-rfc.md §7.5).

Mismo patrón transaccional que `PatientService`/`AIPipelineService`: la
auditoría se escribe y confirma en la MISMA unidad de trabajo que la
operación. Aquí eso significa, en concreto, que el renderizado (que puede
fallar: `DocumentExporter.export()` no está envuelto en el `try`) sucede
ANTES de escribir cualquier fila — si falla, ninguna auditoría llega a
persistirse, nunca queda un `document.exported` falso.

Reutiliza exclusivamente repositorios ya existentes de otros módulos
(`AIArtifactRepository`, `ClinicalSessionRepository`, `PatientRepository`,
`SqlAlchemyClinicRepository`) — mismo nivel de acoplamiento que
`AIPipelineService` con `clinical_sessions`/`patients`/`audit_log`, nunca
sus `Service` públicos (que aplicarían su propia autorización/filtrado,
pensados para otra acción). No se toca `ai_pipeline/service.py`: la
lógica de exportación vive enteramente aquí.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.artifact_repository import AIArtifactRepository
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIArtifactRepository
from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.clinical_sessions.domain.repository import ClinicalSessionRepository
from app.clinical_sessions.infrastructure.repository import SqlAlchemyClinicalSessionRepository
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.authorization import ClinicalDocumentAction, authorize_clinical_document_action
from app.core.current_user import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError
from app.export.domain.entities import build_exportable_document, is_exportable
from app.export.domain.exporter import DocumentExporter
from app.export.infrastructure.pdf_exporter import PdfDocumentExporter
from app.export.infrastructure.text_exporter import TextDocumentExporter
from app.patients.domain.repository import PatientRepository
from app.patients.infrastructure.repository import SqlAlchemyPatientRepository

__all__ = ["ExportFormat", "ExportResult", "ExportService"]

#: `Literal` (no un `StrEnum`) para que FastAPI valide el query param
#: `format` de forma nativa y devuelva 422 ante un valor desconocido sin
#: código de validación propio (encargo 6.6.4, contrato HTTP cerrado).
ExportFormat = Literal["pdf", "text"]

_MEDIA_TYPE_BY_FORMAT: dict[ExportFormat, str] = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
}
_EXTENSION_BY_FORMAT: dict[ExportFormat, str] = {"pdf": "pdf", "text": "txt"}

#: Whitelist estricta para `Content-Disposition`: solo alfanumérico,
#: guion y guion bajo. Cualquier otro carácter (incluidos CR/LF, `/`,
#: `..`, espacios, no-ASCII) se sustituye — impide header injection y
#: path traversal sin necesidad de una librería de slugging genérica.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def _build_filename(
    *,
    patient_internal_code: str,
    artifact_type: AIArtifactType,
    generated_at: datetime,
    export_format: ExportFormat,
) -> str:
    """Determinista y ASCII-safe a partir de datos administrativos
    controlados — nunca `patient_display_name` (texto clínico libre, RFC
    §7.4/encargo 6.6.4: "no usar patient_display_name directamente en
    Content-Disposition")."""
    safe_code = _UNSAFE_FILENAME_CHARS.sub("_", patient_internal_code).strip("_") or "paciente"
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    extension = _EXTENSION_BY_FORMAT[export_format]
    return f"{safe_code}_{artifact_type.value}_{timestamp}.{extension}"


@dataclass(slots=True, frozen=True)
class ExportResult:
    content: bytes
    media_type: str
    filename: str


class ExportService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        artifact_repository: AIArtifactRepository | None = None,
        clinical_session_repository: ClinicalSessionRepository | None = None,
        patient_repository: PatientRepository | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
        text_exporter: DocumentExporter | None = None,
        pdf_exporter: DocumentExporter | None = None,
    ) -> None:
        self._session = session
        self._artifacts = artifact_repository or SqlAlchemyAIArtifactRepository()
        self._clinical_sessions = (
            clinical_session_repository or SqlAlchemyClinicalSessionRepository()
        )
        self._patients = patient_repository or SqlAlchemyPatientRepository()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()
        self._text_exporter = text_exporter or TextDocumentExporter()
        self._pdf_exporter = pdf_exporter or PdfDocumentExporter()

    async def export(
        self,
        current_user: CurrentUser,
        artifact_id: uuid.UUID,
        export_format: ExportFormat,
        request_id: str,
    ) -> ExportResult:
        # Chequeo de rol puro (sin `professional_id`/ownership, RFC §7.5:
        # "admin y audiologist con acceso a la clínica pueden exportar";
        # nunca la restricción de propiedad de sesión de
        # `AIArtifactAction.EDIT/APPROVE`) — se ejecuta ANTES de tocar la
        # BD: falla rápido y no filtra si el recurso existe.
        authorize_clinical_document_action(current_user, ClinicalDocumentAction.EXPORT)

        # Aislamiento de clínica primero: `get_by_id` hace JOIN con
        # `clinical_sessions` y filtra por `clinic_id` — un artefacto de
        # otra clínica es indistinguible de uno inexistente (mismo
        # `NotFoundError`, ver docs/data-model.md). Excluye soft-deleted
        # por defecto (`include_deleted=False`).
        artifact = await self._artifacts.get_by_id(
            self._session, current_user.clinic_id, artifact_id
        )
        if artifact is None:
            raise NotFoundError("Artefacto de IA no encontrado.")

        # El ESTADO manda, nunca el historial: si `current_version_id`
        # apunta a una versión `review_pending` recién editada, el
        # artefacto no es exportable aunque exista una aprobación previa
        # en su historial de versiones (encargo 6.6.4, caso N).
        if not is_exportable(artifact):
            raise ConflictError(
                "El artefacto no tiene una versión aprobada y vigente disponible para exportar."
            )
        assert artifact.current_version_id is not None  # invariante: status == APPROVED

        version = await self._artifacts.get_version_by_id(
            self._session, artifact.current_version_id
        )
        assert version is not None  # invariante: current_version_id ya resuelto

        clinical_session = await self._clinical_sessions.get_by_id(
            self._session, current_user.clinic_id, artifact.clinical_session_id
        )
        # invariante: el artefacto solo existe si la sesión existe
        assert clinical_session is not None

        patient = await self._patients.get_by_id(
            self._session, current_user.clinic_id, clinical_session.patient_id
        )
        assert patient is not None  # invariante: la sesión solo existe si el paciente existe

        clinic = await self._clinics.get_by_id(self._session, current_user.clinic_id)
        assert clinic is not None  # invariante: current_user pertenece a una clínica existente

        generated_at = datetime.now(UTC)
        document = build_exportable_document(
            clinic_name=clinic.name,
            patient_internal_code=patient.internal_code,
            patient_display_name=patient.display_name,
            clinical_session_id=clinical_session.id,
            # Nunca se convierte aquí: `SessionType` no es nullable hoy
            # (ver export/domain/entities.py), así que `.value` siempre
            # produce un `str` real. Si algún día `session_type` admite
            # `None`, este valor debe seguir fluyendo tal cual — el "Sin
            # especificar" lo resuelve cada exportador, no el servicio.
            session_type=clinical_session.session_type.value,
            artifact=artifact,
            version=version,
            generated_at=generated_at,
        )

        exporter = self._pdf_exporter if export_format == "pdf" else self._text_exporter
        # Si `export()` lanza, termina aquí: ni auditoría ni commit se
        # ejecutan (encargo 6.6.4: "si el renderizado falla, no debe
        # quedar un document.exported falso").
        content = exporter.export(document)

        filename = _build_filename(
            patient_internal_code=patient.internal_code,
            artifact_type=artifact.artifact_type,
            generated_at=generated_at,
            export_format=export_format,
        )

        try:
            await self._write_audit(
                current_user,
                request_id,
                action="document.exported",
                entity_id=artifact.id,
                metadata={
                    "clinical_session_id": str(artifact.clinical_session_id),
                    "artifact_id": str(artifact.id),
                    "artifact_type": artifact.artifact_type.value,
                    "version_number": version.version_number,
                    "format": export_format,
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return ExportResult(
            content=content,
            media_type=_MEDIA_TYPE_BY_FORMAT[export_format],
            filename=filename,
        )

    async def _write_audit(
        self,
        current_user: CurrentUser,
        request_id: str,
        *,
        action: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._audit.add(
            self._session,
            AuditLogEntry(
                id=uuid.uuid4(),
                clinic_id=current_user.clinic_id,
                actor_user_id=current_user.id,
                action=action,
                entity_type="ai_artifact",
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
            ),
        )
