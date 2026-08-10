"""Tests de LocalAudioStorage: save/read/delete sobre filesystem real (tmp_path)."""

from __future__ import annotations

import pytest

from app.audio.domain.audio_storage import StorageReference
from app.audio.infrastructure.local_audio_storage import LocalAudioStorage


@pytest.fixture
def storage(tmp_path) -> LocalAudioStorage:
    return LocalAudioStorage(str(tmp_path / "audio"))


def test_crea_el_directorio_base_si_no_existe(tmp_path):
    target_dir = tmp_path / "no-existe-todavia"
    assert not target_dir.exists()
    LocalAudioStorage(str(target_dir))
    assert target_dir.exists()


async def test_save_devuelve_una_referencia_opaca(storage: LocalAudioStorage):
    reference = await storage.save(filename="consulta.mp3", content=b"contenido-ficticio")
    assert isinstance(reference, StorageReference)
    assert reference.value  # no vacío
    assert reference.value.endswith(".mp3")


async def test_save_genera_nombres_distintos_para_el_mismo_filename(storage: LocalAudioStorage):
    ref1 = await storage.save(filename="consulta.mp3", content=b"a")
    ref2 = await storage.save(filename="consulta.mp3", content=b"b")
    assert ref1.value != ref2.value


async def test_read_devuelve_exactamente_el_contenido_guardado(storage: LocalAudioStorage):
    content = b"bytes ficticios de audio, no un paciente real"
    reference = await storage.save(filename="consulta.wav", content=content)
    assert await storage.read(reference) == content


async def test_delete_elimina_el_fichero(storage: LocalAudioStorage, tmp_path):
    reference = await storage.save(filename="consulta.mp3", content=b"x")
    await storage.delete(reference)
    with pytest.raises(FileNotFoundError):
        await storage.read(reference)


async def test_delete_es_idempotente_sobre_una_referencia_ya_borrada(
    storage: LocalAudioStorage,
):
    reference = await storage.save(filename="consulta.mp3", content=b"x")
    await storage.delete(reference)
    await storage.delete(reference)  # no lanza
