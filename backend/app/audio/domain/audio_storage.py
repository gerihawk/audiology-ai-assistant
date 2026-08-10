"""Puerto AudioStorage — ver docs/architecture.md §4.

El dominio de `audio` solo conoce `StorageReference` (valor opaco), nunca
una ruta de disco ni un bucket. MVP: `LocalAudioStorage` (filesystem);
sustituible en el futuro por S3/Azure Blob/GCS sin tocar `audio/service.py`
ni la API — solo esta interfaz y su implementación concreta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class StorageReference:
    value: str


class AudioStorage(Protocol):
    async def save(self, *, filename: str, content: bytes) -> StorageReference: ...

    async def read(self, reference: StorageReference) -> bytes: ...

    async def delete(self, reference: StorageReference) -> None: ...
