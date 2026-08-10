"""Tests de carga del golden dataset: reference.json, metadata.json,
DatasetCase — incluida la ausencia (parcial o total) de esos ficheros."""

from __future__ import annotations

import json

import pytest

from benchmark.dataset import DatasetCaseNotFoundError, list_dataset_case_ids, load_dataset_case
from benchmark.dataset_metadata import MetadataValidationError, load_metadata
from benchmark.reference import ReferenceValidationError, load_reference

_REFERENCE_JSON = {
    "language": "es",
    "speakers": [
        {"id": "audiologist", "label": "Audioprotesista"},
        {"id": "patient", "label": "Paciente"},
    ],
    "segments": [
        {"speaker": "audiologist", "start_ms": None, "end_ms": None, "text": "Buenos días."},
        {"speaker": "patient", "start_ms": 1000, "end_ms": 2000, "text": "Buenos días, doctor."},
    ],
}

_METADATA_JSON = {
    "id": "consulta_ficticia_01",
    "description": "Caso de prueba",
    "language": "es",
    "number_of_speakers": 2,
    "environment": "quiet_clinic",
    "critical_terms": ["acúfenos"],
    "negation_cases": [
        {"concept": "vertigo", "expected": "negated", "patterns": {"negated": ["no vértigo"]}}
    ],
    "laterality_cases": [
        {"concept": "tinnitus", "laterality": "left", "patterns": {"left": ["izquierdo"]}}
    ],
}


# --- reference.json -----------------------------------------------------------


def test_carga_reference_json_valido(tmp_path):
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(_REFERENCE_JSON), encoding="utf-8")

    reference = load_reference(path)

    assert reference.language == "es"
    assert [s.id for s in reference.speakers] == ["audiologist", "patient"]
    assert len(reference.segments) == 2
    assert reference.segments[0].start_ms is None  # timestamps opcionales
    assert reference.segments[1].start_ms == 1000


def test_reference_json_con_speaker_no_declarado_falla():
    data = {**_REFERENCE_JSON, "segments": [{"speaker": "unknown", "text": "hola"}]}
    from benchmark.reference import reference_from_dict

    with pytest.raises(ReferenceValidationError):
        reference_from_dict(data)


def test_reference_json_sin_campo_obligatorio_falla():
    from benchmark.reference import reference_from_dict

    with pytest.raises(ReferenceValidationError):
        reference_from_dict({"language": "es"})


# --- metadata.json --------------------------------------------------------------


def test_carga_metadata_json_valido(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(_METADATA_JSON), encoding="utf-8")

    metadata = load_metadata(path)

    assert metadata.id == "consulta_ficticia_01"
    assert metadata.critical_terms == ["acúfenos"]
    assert metadata.negation_cases[0].concept == "vertigo"
    assert metadata.laterality_cases[0].laterality == "left"


def test_metadata_json_con_environment_invalido_falla():
    from benchmark.dataset_metadata import metadata_from_dict

    data = {**_METADATA_JSON, "environment": "no_existe"}
    with pytest.raises(MetadataValidationError):
        metadata_from_dict(data)


def test_metadata_json_sin_campo_obligatorio_falla():
    from benchmark.dataset_metadata import metadata_from_dict

    with pytest.raises(MetadataValidationError):
        metadata_from_dict({"id": "x"})


# --- DatasetCase / DatasetCaseNotFoundError --------------------------------------


def test_load_dataset_case_completo(tmp_path):
    case_dir = tmp_path / "consulta_ficticia_01"
    case_dir.mkdir()
    (case_dir / "audio.mp3").write_bytes(b"contenido ficticio de audio")
    (case_dir / "reference.json").write_text(json.dumps(_REFERENCE_JSON), encoding="utf-8")
    (case_dir / "metadata.json").write_text(json.dumps(_METADATA_JSON), encoding="utf-8")

    case = load_dataset_case(tmp_path, "consulta_ficticia_01")

    assert case.id == "consulta_ficticia_01"
    assert case.audio_path.name == "audio.mp3"
    assert case.reference is not None
    assert case.metadata is not None


def test_load_dataset_case_sin_reference_ni_metadata_no_falla(tmp_path):
    case_dir = tmp_path / "solo_audio"
    case_dir.mkdir()
    (case_dir / "audio.wav").write_bytes(b"x")

    case = load_dataset_case(tmp_path, "solo_audio")

    assert case.audio_path.name == "audio.wav"
    assert case.reference is None
    assert case.metadata is None


def test_load_dataset_case_sin_audio_lanza_not_found(tmp_path):
    case_dir = tmp_path / "sin_audio"
    case_dir.mkdir()
    (case_dir / "reference.json").write_text(json.dumps(_REFERENCE_JSON), encoding="utf-8")

    with pytest.raises(DatasetCaseNotFoundError):
        load_dataset_case(tmp_path, "sin_audio")


def test_load_dataset_case_carpeta_inexistente_lanza_not_found(tmp_path):
    with pytest.raises(DatasetCaseNotFoundError):
        load_dataset_case(tmp_path, "no_existe")


def test_list_dataset_case_ids(tmp_path):
    (tmp_path / "caso_a").mkdir()
    (tmp_path / "caso_a" / "audio.mp3").write_bytes(b"x")
    (tmp_path / "caso_b").mkdir()
    (tmp_path / "caso_b" / "audio.wav").write_bytes(b"x")
    (tmp_path / "sin_audio").mkdir()  # no debe listarse: no tiene audio

    assert list_dataset_case_ids(tmp_path) == ["caso_a", "caso_b"]


def test_list_dataset_case_ids_carpeta_inexistente_devuelve_vacio(tmp_path):
    assert list_dataset_case_ids(tmp_path / "no_existe") == []
