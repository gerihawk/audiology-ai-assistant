"""Golden dataset de generación — un caso por carpeta bajo
`backend/benchmark/generation_dataset/<case_id>/`:

    generation_dataset/
      consulta_ficticia_01__summary/
        input.json        # transcripción + artifact_type + contexto — versionado
        reference.json       # referencia HUMANA — versionado, nunca generada por IA
        metadata.json           # invariantes clínicas declaradas — versionado

Deliberadamente distinto de `benchmark/dataset/` (benchmark ASR, Fase 5) —
ver docs/generation-benchmark.md §Separación. Un `case_id` = un
`(transcript, artifact_type)`: el mismo transcript ficticio puede
reutilizarse en varias carpetas, una por `artifact_type` evaluado (p. ej.
`consulta_ficticia_01__summary`, `consulta_ficticia_01__missing_information`).

`reference.json`/`metadata.json` son opcionales a nivel de carga, igual
que en el benchmark ASR — un caso sin ellos sigue siendo listable e
inspeccionable. `GenerationBenchmarkRunner` es quien exige `reference`
antes de invocar un modelo real (ver runner.py), nunca este loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchmark.generation.case_metadata import GenerationCaseMetadata, load_case_metadata
from benchmark.generation.input_case import GenerationInput, load_input
from benchmark.generation.reference import GenerationReference, load_reference


class GenerationCaseNotFoundError(FileNotFoundError):
    """No existe `input.json` para `case_id`."""


@dataclass(slots=True, frozen=True)
class GenerationDatasetCase:
    id: str
    input: GenerationInput
    reference: GenerationReference | None
    metadata: GenerationCaseMetadata | None


def load_generation_case(dataset_dir: Path, case_id: str) -> GenerationDatasetCase:
    case_dir = dataset_dir / case_id
    input_path = case_dir / "input.json"
    if not input_path.exists():
        raise GenerationCaseNotFoundError(
            f"No se encontró input.json para '{case_id}' en {case_dir}."
        )
    generation_input = load_input(input_path)

    reference = load_reference(
        case_dir / "reference.json", expected_artifact_type=generation_input.artifact_type
    )

    metadata_path = case_dir / "metadata.json"
    metadata = load_case_metadata(metadata_path) if metadata_path.exists() else None

    return GenerationDatasetCase(
        id=case_id, input=generation_input, reference=reference, metadata=metadata
    )


def list_generation_case_ids(dataset_dir: Path) -> list[str]:
    if not dataset_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in dataset_dir.iterdir()
        if entry.is_dir() and (entry / "input.json").exists()
    )
