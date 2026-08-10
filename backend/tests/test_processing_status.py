"""Tests de la máquina de transiciones de ProcessingStatus (audio_recordings)."""

from __future__ import annotations

import pytest

from app.core.exceptions import ConflictError
from app.core.processing_status import ProcessingStatus, validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProcessingStatus.UPLOADED, ProcessingStatus.VALIDATING),
        (ProcessingStatus.UPLOADED, ProcessingStatus.FAILED),
        (ProcessingStatus.VALIDATING, ProcessingStatus.READY),
        (ProcessingStatus.VALIDATING, ProcessingStatus.FAILED),
        (ProcessingStatus.READY, ProcessingStatus.TRANSCRIBING),
        (ProcessingStatus.READY, ProcessingStatus.DELETED),
        (ProcessingStatus.TRANSCRIBING, ProcessingStatus.TRANSCRIBED),
        (ProcessingStatus.TRANSCRIBING, ProcessingStatus.FAILED),
        (ProcessingStatus.TRANSCRIBED, ProcessingStatus.TRANSCRIBING),
        (ProcessingStatus.TRANSCRIBED, ProcessingStatus.DELETED),
        (ProcessingStatus.FAILED, ProcessingStatus.DELETED),
    ],
)
def test_transiciones_validas(current, target):
    validate_transition(current, target)  # no lanza


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProcessingStatus.UPLOADED, ProcessingStatus.READY),
        (ProcessingStatus.UPLOADED, ProcessingStatus.TRANSCRIBED),
        (ProcessingStatus.READY, ProcessingStatus.TRANSCRIBED),
        (ProcessingStatus.DELETED, ProcessingStatus.READY),
        (ProcessingStatus.FAILED, ProcessingStatus.READY),
    ],
)
def test_transiciones_invalidas(current, target):
    with pytest.raises(ConflictError):
        validate_transition(current, target)
