"""LocalAudioStorage: única implementación de AudioStorage en el MVP.

Filesystem plano bajo `settings.audio_storage_local_dir`. `StorageReference`
guarda únicamente el nombre de fichero generado (nunca la ruta absoluta ni
nada que el dominio de `audio` deba interpretar) — sustituir esto por
S3/Azure Blob/GCS el día que haga falta es una implementación nueva de
`AudioStorage`, sin tocar `audio/service.py` ni la API (ver
docs/architecture.md §4).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import anyio

from app.audio.domain.audio_storage import StorageReference


class LocalAudioStorage:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, *, filename: str, content: bytes) -> StorageReference:
        extension = Path(filename).suffix
        stored_name = f"{uuid.uuid4()}{extension}"
        await anyio.Path(self._base_dir / stored_name).write_bytes(content)
        return StorageReference(value=stored_name)

    async def read(self, reference: StorageReference) -> bytes:
        return await anyio.Path(self._path_for(reference)).read_bytes()

    async def delete(self, reference: StorageReference) -> None:
        path = anyio.Path(self._path_for(reference))
        if await path.exists():
            await path.unlink()

    def _path_for(self, reference: StorageReference) -> Path:
        return self._base_dir / reference.value
