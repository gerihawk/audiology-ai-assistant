"""Primitivas de dominio puras de exportación de documentos clínicos —
Hito 6.6.1 (docs/fase-6-rfc.md §7, scope=session únicamente; scope=patient
es competencia de `clinical_record`, hito 6.7, ver §7.2).

Sin BD, sin HTTP, sin renderizado PDF/texto: dado un `AIArtifact`/
`AIArtifactVersion` ya resueltos y autorizados por el servicio (hito
6.6.3+) y los datos mínimos de cabecera (clínica/paciente/sesión, ya
resueltos como primitivos — nunca las entidades `Clinic`/`Patient`/
`ClinicalSession` completas, para no acoplar `export` a esos módulos de
dominio; mismo criterio que `integrations.domain.session_context.
SessionContext`), construye el DTO canónico (`ExportableDocument`) que
consumirán `PdfDocumentExporter`/`TextDocumentExporter` (hito 6.6.2).

El documento exportado nunca incluye `source_excerpt` (decisión cerrada
de esta fase): `strip_source_excerpt` lo elimina recursivamente de
`content` antes de construir el DTO. La trazabilidad campo a campo sigue
disponible internamente vía `AIArtifactVersion.source_map`, pero no forma
parte del documento exportado.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ai_pipeline.domain.content_walk import iter_dict_nodes
from app.ai_pipeline.domain.entities import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
)

__all__ = [
    "ExportableDocument",
    "is_exportable",
    "strip_source_excerpt",
    "compute_content_hash",
    "build_exportable_document",
]


@dataclass(slots=True, frozen=True)
class ExportableDocument:
    """DTO canónico de exportación (RFC §7.1: "Ambas implementaciones
    consumen un DTO canónico preparado por el servicio de exportación").

    `session_type` se conserva como `str | None` ya resuelto (`.value`),
    no como `SessionType`, mismo criterio que `SessionContext.
    session_type`. RFC §3.3 contempla `None` para datos legacy — aunque
    `ClinicalSessionORM.session_type` es `NOT NULL` hoy, el DTO debe poder
    representar ese estado. La etiqueta "Sin especificar" es
    responsabilidad exclusiva de cada exportador (PDF/texto, hito 6.6.2+),
    nunca de este DTO de dominio."""

    clinic_name: str
    patient_internal_code: str
    patient_display_name: str | None
    clinical_session_id: uuid.UUID
    session_type: str | None
    artifact_type: AIArtifactType
    version_number: int
    approved_by: uuid.UUID
    approved_at: datetime
    content: dict[str, Any]
    content_hash: str
    generated_at: datetime


def is_exportable(artifact: AIArtifact) -> bool:
    """RFC §7.3: solo aprobada, vigente y no eliminada. `status ==
    APPROVED` ya implica "vigente" — ver el docstring de
    `AIArtifactRepository.get_latest_approved`: toda versión nueva
    (generada por IA o editada) reabre `REVIEW_PENDING`, así que nunca hay
    un `APPROVED` que no sea la `current_version_id`. `deleted_at` se
    comprueba aquí de todos modos como defensa en profundidad: esta
    función no debe asumir que `artifact` vino de una consulta que ya
    excluye soft-deleted."""
    return artifact.status == AIArtifactStatus.APPROVED and artifact.deleted_at is None


def strip_source_excerpt(content: dict[str, Any]) -> dict[str, Any]:
    """Elimina recursivamente cualquier clave `source_excerpt` de una copia
    de `content`, sin asumir la forma de un `artifact_type` concreto —
    reutiliza `iter_dict_nodes` (mismo recorrido genérico que ya usa
    `validation_pipeline.py` para localizar bloques con `source_excerpt`).
    El `content` original nunca se muta."""
    sanitized = copy.deepcopy(content)
    for _, node in iter_dict_nodes(sanitized):
        node.pop("source_excerpt", None)
    return sanitized


def compute_content_hash(content: dict[str, Any]) -> str:
    """Hash determinista (SHA-256, hex) del `content` tal y como aparece en
    el documento exportado (ya sin `source_excerpt`) — RFC §7.4 ("hash de
    contenido"). Serialización canónica (`sort_keys`) para que el mismo
    contenido produzca siempre el mismo hash, con independencia del orden
    de inserción de las claves."""
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_exportable_document(
    *,
    clinic_name: str,
    patient_internal_code: str,
    patient_display_name: str | None,
    clinical_session_id: uuid.UUID,
    session_type: str | None,
    artifact: AIArtifact,
    version: AIArtifactVersion,
    generated_at: datetime,
) -> ExportableDocument:
    """Construye el DTO canónico a partir de un artefacto/versión ya
    resueltos y autorizados por el llamador (servicio, hito 6.6.3+).

    Asume las invariantes ya comprobadas por quien llama —
    `is_exportable(artifact)`, `version.id == artifact.current_version_id`,
    `artifact.approved_by`/`approved_at` presentes — y las declara con
    `assert`, mismo criterio que el resto del servicio (ver
    `AIPipelineService._persist_completed_outcome`, "invariante ya
    resuelto"): esta función no decide elegibilidad ni lanza errores de
    dominio propios, solo construye el DTO."""
    assert is_exportable(artifact)  # invariante: comprobado por el llamador
    assert version.id == artifact.current_version_id  # invariante: es la versión vigente
    assert artifact.approved_by is not None  # invariante: status == APPROVED
    assert artifact.approved_at is not None  # invariante: status == APPROVED

    sanitized_content = strip_source_excerpt(version.content)
    return ExportableDocument(
        clinic_name=clinic_name,
        patient_internal_code=patient_internal_code,
        patient_display_name=patient_display_name,
        clinical_session_id=clinical_session_id,
        session_type=session_type,
        artifact_type=artifact.artifact_type,
        version_number=version.version_number,
        approved_by=artifact.approved_by,
        approved_at=artifact.approved_at,
        content=sanitized_content,
        content_hash=compute_content_hash(sanitized_content),
        generated_at=generated_at,
    )
