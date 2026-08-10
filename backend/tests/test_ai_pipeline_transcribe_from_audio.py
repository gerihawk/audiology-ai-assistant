"""Tests de AIPipelineService.transcribe_from_audio (Fase 5): Audio real ->
TranscriptionProvider configurado -> AIArtifact (transcript) -> Review.

Nunca usa AssemblyAI real: siempre un TranscriptionProvider falso
inyectado, tanto a nivel de servicio como (vía dependency_overrides) a
nivel de API.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.entities import AIArtifactStatus, AIArtifactType
from app.ai_pipeline.service import AIPipelineService
from app.audio.domain.audio_storage import AudioStorage, StorageReference
from app.audio.infrastructure.repository import SqlAlchemyAudioRecordingRepository
from app.audio.service import AudioRecordingService, AudioUploadData
from app.core.current_user import CurrentUser
from app.core.deps import get_configured_transcription_provider
from app.core.processing_status import ProcessingStatus
from app.integrations.domain.transcription_provider import (
    TranscriptionInput,
    TranscriptionResult,
)
from app.main import app
from app.patients.domain.entities import Patient
from tests.factories import (
    ClinicWithUsers,
    create_clinic_with_users,
    current_user_from,
    dev_headers,
)

_VALID_CONTENT = b"contenido ficticio de audio, nunca un paciente real" * 10


class _InMemoryAudioStorage:
    """Doble de AudioStorage en memoria — evita tocar el filesystem en tests."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def save(self, *, filename: str, content: bytes) -> StorageReference:
        reference = StorageReference(value=str(uuid.uuid4()))
        self._files[reference.value] = content
        return reference

    async def read(self, reference: StorageReference) -> bytes:
        return self._files[reference.value]

    async def delete(self, reference: StorageReference) -> None:
        self._files.pop(reference.value, None)


class _FakeTranscriptionProvider:
    def __init__(
        self, *, result: TranscriptionResult | None = None, error: Exception | None = None
    ):
        self._result = result
        self._error = error
        self.calls = 0

    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _result(text: str = "texto transcrito de prueba") -> TranscriptionResult:
    return TranscriptionResult(text=text, language="es", confidence=90, duration_ms=5000)


async def _create_session(
    api_client: AsyncClient,
    headers: dict[str, str],
    patient_id: str,
    professional_id: str,
) -> dict:
    payload = {
        "patient_id": patient_id,
        "professional_id": professional_id,
        "session_type": "initial_assessment",
        "status": "completed",
    }
    response = await api_client.post("/api/v1/clinical-sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def clinical_session(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
) -> dict:
    return await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.audiologist.id),
    )


async def _upload_ready_audio(
    db_session: AsyncSession,
    current_user: CurrentUser,
    clinical_session_id: uuid.UUID,
    *,
    audio_storage: AudioStorage,
) -> dict:
    service = AudioRecordingService(db_session, audio_storage=audio_storage)
    recording = await service.upload(
        current_user,
        clinical_session_id,
        AudioUploadData(
            original_filename="consulta.mp3",
            mime_type="audio/mpeg",
            content=_VALID_CONTENT,
            duration_seconds=30,
        ),
        "req-test",
    )
    assert recording.status == ProcessingStatus.READY
    return recording


def _service(
    db_session: AsyncSession, *, provider, audio_storage: AudioStorage
) -> AIPipelineService:
    return AIPipelineService(
        db_session, configured_transcription_provider=provider, audio_storage=audio_storage
    )


# --- Creación y versionado del AIArtifact --------------------------------------


async def test_transcribe_from_audio_crea_el_artefacto_transcript(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    provider = _FakeTranscriptionProvider(result=_result("Primera transcripción."))
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    detail = await service.transcribe_from_audio(admin, recording.id, "req-1")

    assert detail.artifact.artifact_type == AIArtifactType.TRANSCRIPT
    assert detail.artifact.status == AIArtifactStatus.REVIEW_PENDING
    assert detail.current_version.version_number == 1
    assert detail.current_version.content["text"] == "Primera transcripción."
    assert provider.calls == 1

    updated_recording = await SqlAlchemyAudioRecordingRepository().get_by_id(
        db_session, admin.clinic_id, recording.id
    )
    assert updated_recording.status == ProcessingStatus.TRANSCRIBED


async def test_reejecucion_crea_una_nueva_version_y_conserva_el_historial(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    provider_v1 = _FakeTranscriptionProvider(result=_result("Versión 1."))
    service_v1 = _service(db_session, provider=provider_v1, audio_storage=audio_storage)
    detail_v1 = await service_v1.transcribe_from_audio(admin, recording.id, "req-1")
    artifact_id = detail_v1.artifact.id

    provider_v2 = _FakeTranscriptionProvider(result=_result("Versión 2, re-transcrita."))
    service_v2 = _service(db_session, provider=provider_v2, audio_storage=audio_storage)
    detail_v2 = await service_v2.transcribe_from_audio(admin, recording.id, "req-2")

    assert detail_v2.artifact.id == artifact_id  # mismo sobre, nueva versión
    assert detail_v2.current_version.version_number == 2
    assert detail_v2.current_version.content["text"] == "Versión 2, re-transcrita."

    versions = await service_v2.list_versions(admin, artifact_id)
    assert [v.version.version_number for v in versions] == [2, 1]
    assert versions[0].is_current is True
    assert versions[1].is_current is False


# --- Estados inválidos y fallos del proveedor -----------------------------------


async def test_no_se_puede_transcribir_un_audio_sin_subir_correctamente(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    audio_service = AudioRecordingService(db_session, audio_storage=audio_storage)
    failed_recording = await audio_service.upload(
        admin,
        uuid.UUID(clinical_session["id"]),
        AudioUploadData(
            original_filename="malo.exe",
            mime_type="application/octet-stream",
            content=b"x",
            duration_seconds=10,
        ),
        "req-upload",
    )
    assert failed_recording.status == ProcessingStatus.FAILED

    provider = _FakeTranscriptionProvider(result=_result())
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import ConflictError

    with pytest.raises(ConflictError):
        await service.transcribe_from_audio(admin, failed_recording.id, "req-2")
    assert provider.calls == 0


async def test_fallo_del_proveedor_persiste_el_fallo_y_lanza_conflicterror(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    provider = _FakeTranscriptionProvider(error=RuntimeError("fallo simulado del proveedor"))
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import ConflictError

    with pytest.raises(ConflictError, match="fallo simulado del proveedor"):
        await service.transcribe_from_audio(admin, recording.id, "req-1")

    updated_recording = await SqlAlchemyAudioRecordingRepository().get_by_id(
        db_session, admin.clinic_id, recording.id
    )
    assert updated_recording.status == ProcessingStatus.FAILED
    assert "fallo simulado" in updated_recording.failure_reason


async def test_no_se_puede_transcribir_dos_veces_a_la_vez(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    """Simula un ai_pipeline_run ya en curso insertándolo directamente
    (en este backend síncrono, `run_pipeline`/`transcribe_from_audio`
    nunca dejan uno a medias de forma natural — ver
    docs/ai-pipeline-architecture.md §8)."""
    from datetime import UTC, datetime

    from app.ai_pipeline.domain.entities import AIPipelineRun, AIPipelineRunStatus
    from app.ai_pipeline.infrastructure.repository import SqlAlchemyAIPipelineRunRepository

    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    await SqlAlchemyAIPipelineRunRepository().add(
        db_session,
        AIPipelineRun(
            id=uuid.uuid4(),
            clinical_session_id=uuid.UUID(clinical_session["id"]),
            triggered_by=admin.id,
            status=AIPipelineRunStatus.PROCESSING,
            started_at=datetime.now(UTC),
            completed_at=None,
            request_id="req-en-curso",
        ),
    )
    await db_session.commit()

    provider = _FakeTranscriptionProvider(result=_result())
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import ConflictError

    with pytest.raises(ConflictError, match="en curso"):
        await service.transcribe_from_audio(admin, recording.id, "req-2")
    assert provider.calls == 0


# --- Rollback ------------------------------------------------------------------


async def test_un_fallo_inesperado_revierte_toda_la_transaccion(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    class _BrokenAuditRepository:
        async def add(self, session, entry):
            raise RuntimeError("fallo inesperado no relacionado con el proveedor")

    provider = _FakeTranscriptionProvider(result=_result("no debería persistir"))
    service = AIPipelineService(
        db_session,
        configured_transcription_provider=provider,
        audio_storage=audio_storage,
        audit_repository=_BrokenAuditRepository(),
    )

    with pytest.raises(RuntimeError, match="fallo inesperado"):
        await service.transcribe_from_audio(admin, recording.id, "req-1")

    # Tras el rollback, ni el audio ni el artefacto reflejan el intento fallido.
    reloaded_recording = await SqlAlchemyAudioRecordingRepository().get_by_id(
        db_session, admin.clinic_id, recording.id
    )
    assert reloaded_recording.status == ProcessingStatus.READY

    artifacts = await service.list_artifacts(admin, uuid.UUID(clinical_session["id"]))
    transcript_artifacts = [
        a for a in artifacts if a.artifact.artifact_type == AIArtifactType.TRANSCRIPT
    ]
    assert transcript_artifacts == []


# --- Permisos --------------------------------------------------------------------


async def test_viewer_no_puede_transcribir(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    provider = _FakeTranscriptionProvider(result=_result())
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import ForbiddenError

    viewer = current_user_from(clinic_with_users.viewer)
    with pytest.raises(ForbiddenError):
        await service.transcribe_from_audio(viewer, recording.id, "req-1")


async def test_audiologist_no_puede_transcribir_audio_de_otro_profesional(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
):
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),  # sesión del admin, no del audiologist
    )
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(session["id"]), audio_storage=audio_storage
    )

    provider = _FakeTranscriptionProvider(result=_result())
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import ForbiddenError

    audiologist = current_user_from(clinic_with_users.audiologist)
    with pytest.raises(ForbiddenError):
        await service.transcribe_from_audio(audiologist, recording.id, "req-1")


async def test_grabacion_de_otra_clinica_devuelve_404(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    audio_storage = _InMemoryAudioStorage()
    admin = current_user_from(clinic_with_users.admin)
    recording = await _upload_ready_audio(
        db_session, admin, uuid.UUID(clinical_session["id"]), audio_storage=audio_storage
    )

    other_clinic = await create_clinic_with_users(db_session)
    other_admin = current_user_from(other_clinic.admin)

    provider = _FakeTranscriptionProvider(result=_result())
    service = _service(db_session, provider=provider, audio_storage=audio_storage)

    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await service.transcribe_from_audio(other_admin, recording.id, "req-1")


# --- API end-to-end (dependency override, sin AssemblyAI real) -----------------


async def test_endpoint_transcribe_usa_el_provider_inyectado_por_configuracion(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    provider = _FakeTranscriptionProvider(result=_result("Transcripción vía API."))

    app.dependency_overrides[get_configured_transcription_provider] = lambda: provider
    try:
        headers = dev_headers(clinic_with_users.admin)
        upload_response = await api_client.post(
            f"/api/v1/clinical-sessions/{clinical_session['id']}/audio-recordings",
            headers=headers,
            files={"file": ("consulta.mp3", _VALID_CONTENT, "audio/mpeg")},
            data={"duration_seconds": "30"},
        )
        assert upload_response.status_code == 201, upload_response.text
        recording_id = upload_response.json()["id"]

        transcribe_response = await api_client.post(
            f"/api/v1/audio-recordings/{recording_id}/transcribe", headers=headers
        )
        assert transcribe_response.status_code == 200, transcribe_response.text
        body = transcribe_response.json()
        assert body["artifact_type"] == "transcript"
        assert body["content"]["text"] == "Transcripción vía API."
        assert provider.calls == 1
    finally:
        app.dependency_overrides.pop(get_configured_transcription_provider, None)
