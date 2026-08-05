"""Máquina de estados de ClinicalSession. Ver docs/data-model.md §8.

Toda transición y regla de edición se valida aquí, no en el router. Cada
función lanza `ConflictError` (409) ante una operación inválida para el
estado actual, o devuelve una señal de "no-op idempotente" cuando la
operación ya está satisfecha.
"""

from __future__ import annotations

from app.clinical_sessions.domain.entities import ClinicalSessionStatus
from app.core.exceptions import ConflictError

#: Estado de destino de cada acción de transición.
_TARGET_STATUS: dict[str, ClinicalSessionStatus] = {
    "start": ClinicalSessionStatus.IN_PROGRESS,
    "complete": ClinicalSessionStatus.COMPLETED,
    "submit_review": ClinicalSessionStatus.REVIEW_PENDING,
    "review": ClinicalSessionStatus.REVIEWED,
    "cancel": ClinicalSessionStatus.CANCELLED,
}

#: Estados de origen válidos para cada acción de transición.
_VALID_SOURCES: dict[str, frozenset[ClinicalSessionStatus]] = {
    "start": frozenset({ClinicalSessionStatus.SCHEDULED}),
    "complete": frozenset({ClinicalSessionStatus.IN_PROGRESS}),
    "submit_review": frozenset({ClinicalSessionStatus.COMPLETED}),
    "review": frozenset({ClinicalSessionStatus.REVIEW_PENDING}),
    "cancel": frozenset({ClinicalSessionStatus.SCHEDULED, ClinicalSessionStatus.IN_PROGRESS}),
}

#: Estados desde los que se permite archivar (nunca desde review_pending).
ARCHIVABLE_STATUSES: frozenset[ClinicalSessionStatus] = frozenset(
    {
        ClinicalSessionStatus.COMPLETED,
        ClinicalSessionStatus.REVIEWED,
        ClinicalSessionStatus.CANCELLED,
    }
)

#: Estados en los que la sesión no admite ninguna edición.
_NOT_EDITABLE_STATUSES: frozenset[ClinicalSessionStatus] = frozenset(
    {ClinicalSessionStatus.REVIEWED, ClinicalSessionStatus.CANCELLED}
)

#: En review_pending, únicamente estos campos son editables.
RESTRICTED_EDITABLE_FIELDS: frozenset[str] = frozenset({"title", "administrative_notes"})


def resolve_transition(
    action: str, current_status: ClinicalSessionStatus
) -> ClinicalSessionStatus | None:
    """Resuelve una transición de estado.

    Devuelve el nuevo `ClinicalSessionStatus` a aplicar, o `None` si la
    transición es un no-op idempotente (el estado actual ya es el
    destino). Lanza `ConflictError` si la transición no es válida desde
    el estado actual.
    """
    target = _TARGET_STATUS[action]
    if current_status == target:
        return None
    if current_status not in _VALID_SOURCES[action]:
        raise ConflictError(
            f"No se puede ejecutar '{action}' desde el estado '{current_status.value}'."
        )
    return target


def resolve_archive(current_status: ClinicalSessionStatus, is_archived: bool) -> bool:
    """Devuelve True si hay que archivar, False si es un no-op idempotente.

    Lanza `ConflictError` si el estado actual no admite archivado.
    """
    if is_archived:
        return False
    if current_status not in ARCHIVABLE_STATUSES:
        raise ConflictError(f"No se puede archivar una sesión en estado '{current_status.value}'.")
    return True


def resolve_restore(is_archived: bool) -> bool:
    """Devuelve True si hay que restaurar, False si es un no-op idempotente."""
    return is_archived


def validate_editable_fields(
    status: ClinicalSessionStatus, is_archived: bool, provided_fields: set[str]
) -> None:
    """Lanza `ConflictError` si `provided_fields` no son editables en el
    estado/archivado actual de la sesión."""
    if is_archived:
        raise ConflictError("No se puede editar una sesión archivada.")
    if status in _NOT_EDITABLE_STATUSES:
        raise ConflictError(f"No se puede editar una sesión en estado '{status.value}'.")
    if status == ClinicalSessionStatus.REVIEW_PENDING:
        disallowed = provided_fields - RESTRICTED_EDITABLE_FIELDS
        if disallowed:
            allowed = ", ".join(sorted(RESTRICTED_EDITABLE_FIELDS))
            raise ConflictError(f"En 'review_pending' solo se pueden editar los campos: {allowed}.")
