"""Tests de integración de la API de audio_recordings (Fase 5) contra Postgres real."""

from __future__ import annotations

import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, create_clinic_with_users, dev_headers

_VALID_CONTENT = b"contenido ficticio de audio, nunca un paciente real" * 10


async def _create_session(
    api_client: AsyncClient,
    headers: dict[str, str],
    patient_id: str,
    professional_id: str,
    **overrides,
) -> dict:
    payload = {
        "patient_id": patient_id,
        "professional_id": professional_id,
        "session_type": "initial_assessment",
        "status": "completed",
    } | overrides
    response = await api_client.post("/api/v1/clinical-sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _upload(
    api_client: AsyncClient,
    headers: dict[str, str],
    session_id: str,
    *,
    filename: str = "consulta_ficticia.mp3",
    content: bytes = _VALID_CONTENT,
    mime_type: str = "audio/mpeg",
    duration_seconds: int = 30,
) -> tuple[int, dict]:
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session_id}/audio-recordings",
        headers=headers,
        files={"file": (filename, content, mime_type)},
        data={"duration_seconds": str(duration_seconds)},
    )
    return response.status_code, response.json()


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


# --- Subida ------------------------------------------------------------------


async def test_upload_valido_queda_ready_con_checksum_y_duracion(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, body = await _upload(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"]
    )

    assert status_code == 201, body
    assert body["status"] == "ready"
    assert body["failure_reason"] is None
    assert body["duration_seconds"] == 30
    assert body["size_bytes"] == len(_VALID_CONTENT)
    assert body["checksum"] == hashlib.sha256(_VALID_CONTENT).hexdigest()
    assert body["storage_provider"] == "local"
    assert "storage_reference" not in body  # nunca se expone, es opaco


async def test_upload_con_extension_no_permitida_queda_failed(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, body = await _upload(
        api_client,
        dev_headers(clinic_with_users.admin),
        clinical_session["id"],
        filename="malware.exe",
        mime_type="application/octet-stream",
    )

    assert status_code == 201, body  # la subida en sí no falla como operación HTTP
    assert body["status"] == "failed"
    assert body["failure_reason"] is not None
    assert body["duration_seconds"] is None


async def test_upload_con_duracion_invalida_queda_failed(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, body = await _upload(
        api_client, dev_headers(clinic_with_users.admin), clinical_session["id"], duration_seconds=0
    )

    assert status_code == 201, body
    assert body["status"] == "failed"
    assert "duración" in body["failure_reason"].lower()


async def test_upload_sobre_sesion_inexistente_devuelve_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    status_code, body = await _upload(
        api_client,
        dev_headers(clinic_with_users.admin),
        "00000000-0000-0000-0000-000000000000",
    )
    assert status_code == 404


# --- Listado -------------------------------------------------------------------


async def test_list_devuelve_las_grabaciones_mas_reciente_primero(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    await _upload(api_client, headers, clinical_session["id"], filename="primero.mp3")
    await _upload(api_client, headers, clinical_session["id"], filename="segundo.mp3")

    response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/audio-recordings", headers=headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["original_filename"] == "segundo.mp3"
    assert items[1]["original_filename"] == "primero.mp3"


async def test_list_vacio_para_una_sesion_sin_audio(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/audio-recordings",
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


# --- Eliminación ---------------------------------------------------------------


async def test_delete_marca_deleted_e_invalida_la_referencia(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, uploaded = await _upload(api_client, headers, clinical_session["id"])

    response = await api_client.delete(
        f"/api/v1/audio-recordings/{uploaded['id']}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deleted"
    assert body["deleted_at"] is not None


async def test_delete_es_idempotente(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers = dev_headers(clinic_with_users.admin)
    _, uploaded = await _upload(api_client, headers, clinical_session["id"])

    first = await api_client.delete(f"/api/v1/audio-recordings/{uploaded['id']}", headers=headers)
    second = await api_client.delete(f"/api/v1/audio-recordings/{uploaded['id']}", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "deleted"


async def test_delete_de_audio_inexistente_devuelve_404(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers
):
    response = await api_client.delete(
        "/api/v1/audio-recordings/00000000-0000-0000-0000-000000000000",
        headers=dev_headers(clinic_with_users.admin),
    )
    assert response.status_code == 404


# --- Permisos --------------------------------------------------------------------


async def test_viewer_no_puede_subir_audio(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    status_code, _ = await _upload(
        api_client, dev_headers(clinic_with_users.viewer), clinical_session["id"]
    )
    assert status_code == 403


async def test_viewer_puede_listar(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/audio-recordings",
        headers=dev_headers(clinic_with_users.viewer),
    )
    assert response.status_code == 200


async def test_viewer_no_puede_eliminar(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, clinical_session: dict
):
    headers_admin = dev_headers(clinic_with_users.admin)
    _, uploaded = await _upload(api_client, headers_admin, clinical_session["id"])

    response = await api_client.delete(
        f"/api/v1/audio-recordings/{uploaded['id']}", headers=dev_headers(clinic_with_users.viewer)
    )
    assert response.status_code == 403


async def test_audiologist_no_puede_subir_audio_a_sesion_de_otro_profesional(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    # La sesión pertenece al admin (professional_id = admin), no al audiologist.
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.admin.id),
    )
    status_code, _ = await _upload(
        api_client, dev_headers(clinic_with_users.audiologist), session["id"]
    )
    assert status_code == 403


async def test_audiologist_puede_subir_y_eliminar_en_sus_propias_sesiones(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    session = await _create_session(
        api_client,
        dev_headers(clinic_with_users.admin),
        str(patient.id),
        str(clinic_with_users.audiologist.id),
    )
    headers = dev_headers(clinic_with_users.audiologist)
    status_code, uploaded = await _upload(api_client, headers, session["id"])
    assert status_code == 201

    response = await api_client.delete(
        f"/api/v1/audio-recordings/{uploaded['id']}", headers=headers
    )
    assert response.status_code == 200


# --- Aislamiento entre clínicas ---------------------------------------------------


async def test_audio_de_otra_clinica_devuelve_404(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    clinical_session: dict,
):
    headers_own_clinic = dev_headers(clinic_with_users.admin)
    _, uploaded = await _upload(api_client, headers_own_clinic, clinical_session["id"])

    other_clinic = await create_clinic_with_users(db_session)
    headers_other_clinic = dev_headers(other_clinic.admin)

    get_response = await api_client.get(
        f"/api/v1/clinical-sessions/{clinical_session['id']}/audio-recordings",
        headers=headers_other_clinic,
    )
    assert get_response.status_code == 404

    delete_response = await api_client.delete(
        f"/api/v1/audio-recordings/{uploaded['id']}", headers=headers_other_clinic
    )
    assert delete_response.status_code == 404


async def test_sesion_de_otra_clinica_no_permite_subir(
    api_client: AsyncClient,
    db_session: AsyncSession,
    clinical_session: dict,
):
    other_clinic = await create_clinic_with_users(db_session)
    status_code, _ = await _upload(
        api_client, dev_headers(other_clinic.admin), clinical_session["id"]
    )
    assert status_code == 404
