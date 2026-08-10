"""`ProcessingStatus`: reservado exclusivamente a `audio_recordings`.

Ver docs/data-model.md §6 y docs/architecture.md §5. Toda otra entidad con
ciclo de vida propio (`clinical_sessions`, artefactos de IA) tiene su
propia máquina de estados — no comparte este enumerado.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import ConflictError


class ProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    READY = "ready"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED = "failed"
    DELETED = "deleted"


#: Transiciones válidas (ver docs/data-model.md §6). `DELETED` es
#: alcanzable desde cualquier estado no terminal: un audio puede
#: eliminarse manualmente en cualquier momento (subida fallida incluida),
#: no solo tras completar el ciclo de transcripción.
_VALID_TRANSITIONS: dict[ProcessingStatus, frozenset[ProcessingStatus]] = {
    ProcessingStatus.UPLOADED: frozenset(
        {ProcessingStatus.VALIDATING, ProcessingStatus.FAILED, ProcessingStatus.DELETED}
    ),
    ProcessingStatus.VALIDATING: frozenset(
        {ProcessingStatus.READY, ProcessingStatus.FAILED, ProcessingStatus.DELETED}
    ),
    ProcessingStatus.READY: frozenset({ProcessingStatus.TRANSCRIBING, ProcessingStatus.DELETED}),
    # TRANSCRIBED -> TRANSCRIBING está permitido deliberadamente: permite
    # re-transcribir el mismo audio (p. ej. tras cambiar TRANSCRIPTION_PROVIDER
    # o para comparar proveedores vía benchmark) sin volver a subir el fichero.
    ProcessingStatus.TRANSCRIBING: frozenset(
        {ProcessingStatus.TRANSCRIBED, ProcessingStatus.FAILED, ProcessingStatus.DELETED}
    ),
    ProcessingStatus.TRANSCRIBED: frozenset(
        {ProcessingStatus.TRANSCRIBING, ProcessingStatus.DELETED}
    ),
    ProcessingStatus.FAILED: frozenset({ProcessingStatus.DELETED}),
    ProcessingStatus.DELETED: frozenset(),
}


def validate_transition(current: ProcessingStatus, target: ProcessingStatus) -> None:
    """Lanza `ConflictError` si `current -> target` no es una transición válida."""
    if target not in _VALID_TRANSITIONS[current]:
        raise ConflictError(f"No se puede pasar de '{current.value}' a '{target.value}'.")
