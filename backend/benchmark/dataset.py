"""Golden dataset — un caso por carpeta bajo `benchmark/dataset/<id>/`.
Ver docs/transcription-benchmark.md §Golden dataset.

    benchmark/dataset/
      consulta_ficticia_01/
        audio.mp3        # NO versionado (ver .gitignore)
        reference.json     # versionado — transcripción manual, fuente de verdad
        metadata.json        # versionado — términos críticos, casos de negación/lateralidad...

`reference.json`/`metadata.json` son opcionales por caso: un caso sin
ellos sigue siendo transcribible, simplemente no se calculan las métricas
que dependen de esos ficheros (WER, terminología, negaciones,
lateralidad, atribución de hablante) — ver report.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchmark.dataset_metadata import DatasetMetadata, load_metadata
from benchmark.reference import Reference, load_reference

_AUDIO_FILENAMES = ("audio.mp3", "audio.wav", "audio.m4a", "audio.ogg", "audio.webm")


class DatasetCaseNotFoundError(FileNotFoundError):
    """No existe una carpeta de caso ni un fichero de audio para `audio_id`."""


@dataclass(slots=True, frozen=True)
class DatasetCase:
    id: str
    audio_path: Path
    reference: Reference | None
    metadata: DatasetMetadata | None


def _find_audio_file(case_dir: Path) -> Path | None:
    for filename in _AUDIO_FILENAMES:
        candidate = case_dir / filename
        if candidate.exists():
            return candidate
    return None


def load_dataset_case(dataset_dir: Path, audio_id: str) -> DatasetCase:
    case_dir = dataset_dir / audio_id
    audio_path = _find_audio_file(case_dir) if case_dir.is_dir() else None
    if audio_path is None:
        raise DatasetCaseNotFoundError(
            f"No se encontró audio para '{audio_id}' en {case_dir} "
            f"(esperaba uno de: {', '.join(_AUDIO_FILENAMES)})."
        )

    reference_path = case_dir / "reference.json"
    reference = load_reference(reference_path) if reference_path.exists() else None

    metadata_path = case_dir / "metadata.json"
    metadata = load_metadata(metadata_path) if metadata_path.exists() else None

    return DatasetCase(id=audio_id, audio_path=audio_path, reference=reference, metadata=metadata)


def list_dataset_case_ids(dataset_dir: Path) -> list[str]:
    if not dataset_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in dataset_dir.iterdir()
        if entry.is_dir() and _find_audio_file(entry) is not None
    )
