"""Primitivas de dominio puras de la historia clínica longitudinal —
Hito 6.7.1 (docs/fase-6-rfc.md §3.4/§8, docs/development-plan.md §6.7).

`clinical_record` es un módulo independiente de agregación de solo
lectura: sin ORM, sin tabla, sin persistencia propia (RFC §3.4/§8,
Decisión cerrada 15). RFC §3.4 solo declara `patients`,
`clinical_sessions` y `ai_pipeline` como dependencias de origen — nunca
`export` (módulo hermano, no padre): por eso este módulo no importa nada
de `app.export`, aunque resuelva el mismo tipo de necesidades
(elegibilidad, saneado de `source_excerpt`) reimplementándolas sobre las
mismas primitivas compartidas de `ai_pipeline`. El servicio que resuelve
`patients`/`clinical_sessions`/`ai_pipeline` y llama a estas funciones
puras es competencia del hito 6.7.2+, igual que
`ClinicalRecordExportBundle`/`export_many()`.

Estructura longitudinal: paciente → sesiones (orden `created_at ASC, id
ASC`) → documentos aprobados de cada sesión (orden
`PIPELINE_STEP_ORDER`). Solo entran artefactos `APPROVED` y no
eliminados — los 7 `AIArtifactType` actuales, sin exclusiones por tipo
(RFC §8, punto 4: "excluye borradores, rechazados y eliminados"). Las
`ANAMNESIS` históricas permanecen visibles en su sesión original; solo
la aprobación más reciente de todo el paciente (`approved_at DESC`,
mismo criterio que `AIArtifactRepository.get_latest_approved`) lleva
`is_current_baseline=True`. Ningún otro `artifact_type` tiene concepto
de baseline vigente.

Nunca expone `source_excerpt`, `source_map` ni metadata interna de
generación (coste, proveedor, prompt, confidence) — mismo criterio de
minimización que `export.domain.entities.ExportableDocument`.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ai_pipeline.domain.content_walk import iter_dict_nodes
from app.ai_pipeline.domain.entities import (
    PIPELINE_STEP_ORDER,
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    AIArtifactVersion,
)

__all__ = [
    "ClinicalRecordPatientRef",
    "ClinicalRecordDocument",
    "ClinicalRecordSessionEntry",
    "ClinicalRecordPage",
    "LoadedSessionArtifacts",
    "is_eligible_artifact",
    "strip_source_excerpt",
    "sort_documents_by_pipeline_order",
    "find_current_anamnesis_baseline",
    "build_session_entries",
    "build_clinical_record_page",
]


@dataclass(slots=True, frozen=True)
class ClinicalRecordPatientRef:
    """Identidad mínima del paciente, ya resuelta como primitivos — nunca
    la entidad `Patient` completa (mismo criterio que `ExportableDocument`,
    RFC §3.4: no acoplar este módulo a `patients.domain`)."""

    patient_id: uuid.UUID
    internal_code: str
    display_name: str | None


@dataclass(slots=True, frozen=True)
class ClinicalRecordDocument:
    """Un documento aprobado dentro de una sesión. `is_current_baseline`
    solo tiene semántica útil para `ANAMNESIS` — para el resto de
    `artifact_type` siempre es `False` (decisión cerrada: `SESSION_NOTES`
    y los demás tipos no tienen concepto de baseline vigente)."""

    ai_artifact_id: uuid.UUID
    artifact_type: AIArtifactType
    version_number: int
    approved_by: uuid.UUID
    approved_at: datetime
    content: dict[str, Any]
    is_current_baseline: bool


@dataclass(slots=True, frozen=True)
class ClinicalRecordSessionEntry:
    """Una sesión clínica del expediente, con sus documentos aprobados ya
    ordenados por `PIPELINE_STEP_ORDER`. `session_type` se conserva como
    `str | None` ya resuelto — `None` es un caso legacy válido; la
    etiqueta "Sin especificar" es responsabilidad exclusiva de
    presentación/exportación, nunca de este DTO (mismo criterio que
    `ExportableDocument.session_type`)."""

    clinical_session_id: uuid.UUID
    session_type: str | None
    created_at: datetime
    documents: tuple[ClinicalRecordDocument, ...]


@dataclass(slots=True, frozen=True)
class ClinicalRecordPage:
    """Página longitudinal completa de un paciente. `total`/`limit`/
    `offset` son metadata de paginación ya resuelta por el llamador — la
    consulta real de `ClinicalSession` es competencia del servicio de
    6.7.2+, no de este módulo."""

    patient: ClinicalRecordPatientRef
    sessions: tuple[ClinicalRecordSessionEntry, ...]
    total: int
    limit: int
    offset: int


@dataclass(slots=True, frozen=True)
class LoadedSessionArtifacts:
    """Entrada de `build_session_entries`/`build_clinical_record_page`:
    una sesión ya cargada junto a los pares `(AIArtifact,
    AIArtifactVersion)` de su versión vigente — nunca la entidad
    `ClinicalSession` completa (mismo criterio que
    `ClinicalRecordPatientRef`). El llamador decide qué versión es la
    vigente (`version.id == artifact.current_version_id`); este módulo no
    lo vuelve a resolver ni consulta nada."""

    clinical_session_id: uuid.UUID
    session_type: str | None
    created_at: datetime
    artifacts: tuple[tuple[AIArtifact, AIArtifactVersion], ...]


def is_eligible_artifact(artifact: AIArtifact) -> bool:
    """Elegibilidad para el expediente: aprobado y no eliminado — misma
    semántica cerrada en el hito 6.6 (`export.domain.entities.
    is_exportable`), reimplementada aquí en vez de importada porque RFC
    §3.4 no declara `export` como dependencia de `clinical_record`.
    `status == APPROVED` ya implica "vigente": ver docstring de
    `AIArtifactRepository.get_latest_approved`. `deleted_at` se comprueba
    de todos modos como defensa en profundidad."""
    return artifact.status == AIArtifactStatus.APPROVED and artifact.deleted_at is None


def strip_source_excerpt(content: dict[str, Any]) -> dict[str, Any]:
    """Elimina recursivamente cualquier clave `source_excerpt` de una
    copia de `content`. Reutiliza `iter_dict_nodes` (misma primitiva
    genérica que ya usan `validation_pipeline.py` y
    `export.domain.entities.strip_source_excerpt`) en vez de reimplementar
    el recorrido recursivo. El `content` original nunca se muta."""
    sanitized = copy.deepcopy(content)
    for _, node in iter_dict_nodes(sanitized):
        node.pop("source_excerpt", None)
    return sanitized


def sort_documents_by_pipeline_order(
    documents: Sequence[ClinicalRecordDocument],
) -> tuple[ClinicalRecordDocument, ...]:
    """Orden estable por `PIPELINE_STEP_ORDER` — los 7 `AIArtifactType`
    actuales tienen entrada en esa tupla, así que no hace falta un valor
    por defecto para tipos desconocidos."""
    order_index = {artifact_type: i for i, artifact_type in enumerate(PIPELINE_STEP_ORDER)}
    return tuple(sorted(documents, key=lambda doc: order_index[doc.artifact_type]))


def find_current_anamnesis_baseline(
    anamnesis_artifacts: Sequence[AIArtifact],
) -> AIArtifact | None:
    """Identifica la `ANAMNESIS` vigente entre las ya elegibles (aprobadas,
    no eliminadas) de TODO el paciente — mismo criterio que
    `AIArtifactRepository.get_latest_approved` (`approved_at DESC`), sin
    consultar BD desde dominio: el llamador ya cargó y filtró la lista.

    Empate exacto en `approved_at` (dos aprobaciones al mismo instante) se
    resuelve por `id` como desempate determinista — no hay ninguna otra
    señal temporal disponible en el dominio para desambiguar, pero el
    resultado debe ser reproducible entre llamadas con la misma entrada.
    `None` si la lista está vacía."""
    if not anamnesis_artifacts:
        return None
    return max(anamnesis_artifacts, key=lambda artifact: (artifact.approved_at, artifact.id))


def _build_document(
    artifact: AIArtifact, version: AIArtifactVersion, *, is_current_baseline: bool
) -> ClinicalRecordDocument:
    assert is_eligible_artifact(artifact)  # invariante: comprobado por el llamador
    assert version.id == artifact.current_version_id  # invariante: es la versión vigente
    assert artifact.approved_by is not None  # invariante: status == APPROVED
    assert artifact.approved_at is not None  # invariante: status == APPROVED
    return ClinicalRecordDocument(
        ai_artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        version_number=version.version_number,
        approved_by=artifact.approved_by,
        approved_at=artifact.approved_at,
        content=strip_source_excerpt(version.content),
        is_current_baseline=is_current_baseline,
    )


def build_session_entries(
    sessions: Sequence[LoadedSessionArtifacts],
) -> tuple[ClinicalRecordSessionEntry, ...]:
    """Construye las entradas longitudinales (sesión → documentos
    aprobados) a partir de objetos ya cargados: filtra por elegibilidad,
    identifica la `ANAMNESIS` vigente de TODO el paciente (cruza
    sesiones) y ordena documentos por `PIPELINE_STEP_ORDER` y sesiones por
    `created_at ASC, id ASC`. No muta ninguno de los objetos de entrada."""
    eligible_anamnesis = [
        artifact
        for session in sessions
        for artifact, _ in session.artifacts
        if artifact.artifact_type == AIArtifactType.ANAMNESIS and is_eligible_artifact(artifact)
    ]
    baseline = find_current_anamnesis_baseline(eligible_anamnesis)

    entries = [
        ClinicalRecordSessionEntry(
            clinical_session_id=session.clinical_session_id,
            session_type=session.session_type,
            created_at=session.created_at,
            documents=sort_documents_by_pipeline_order(
                [
                    _build_document(
                        artifact,
                        version,
                        is_current_baseline=baseline is not None and artifact.id == baseline.id,
                    )
                    for artifact, version in session.artifacts
                    if is_eligible_artifact(artifact)
                ]
            ),
        )
        for session in sessions
    ]

    return tuple(sorted(entries, key=lambda entry: (entry.created_at, entry.clinical_session_id)))


def build_clinical_record_page(
    *,
    patient: ClinicalRecordPatientRef,
    sessions: Sequence[LoadedSessionArtifacts],
    total: int,
    limit: int,
    offset: int,
) -> ClinicalRecordPage:
    """Envuelve `build_session_entries` con la identidad del paciente y la
    metadata de paginación ya resuelta por el llamador."""
    return ClinicalRecordPage(
        patient=patient,
        sessions=build_session_entries(sessions),
        total=total,
        limit=limit,
        offset=offset,
    )
