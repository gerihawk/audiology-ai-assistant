"""Tests de carga del golden dataset de generación — Fase 6.2. Sin red,
sin base de datos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai_pipeline.domain.entities import AIArtifactType
from benchmark.generation.dataset import (
    GenerationCaseNotFoundError,
    list_generation_case_ids,
    load_generation_case,
)
from benchmark.generation.input_case import InputValidationError, input_from_dict
from benchmark.generation.reference import ReferenceValidationError, reference_from_dict

_REAL_DATASET_DIR = Path(__file__).resolve().parent.parent / "benchmark" / "generation_dataset"


def _minimal_input(**overrides) -> dict:
    data = {
        "id": "case_x",
        "language": "es",
        "artifact_type": "summary",
        "transcript": "hola",
    }
    data.update(overrides)
    return data


class TestInputCase:
    def test_input_valido_minimo(self):
        result = input_from_dict(_minimal_input())
        assert result.artifact_type is AIArtifactType.SUMMARY
        assert result.context == {}
        assert result.prompt_template is None
        assert result.transcript_segments == ()

    def test_input_falta_campo_obligatorio(self):
        data = _minimal_input()
        del data["transcript"]
        with pytest.raises(InputValidationError):
            input_from_dict(data)

    def test_input_artifact_type_invalido(self):
        # "session_notes" fue el ejemplo histórico de tipo inválido hasta
        # la Fase 6.4.3 — ahora es un AIArtifactType real.
        with pytest.raises(InputValidationError):
            input_from_dict(_minimal_input(artifact_type="tipo_inexistente"))

    def test_input_context_no_str_rechazado(self):
        with pytest.raises(InputValidationError):
            input_from_dict(_minimal_input(context={"summary_text": 123}))

    def test_input_con_prompt_template_pin(self):
        result = input_from_dict(_minimal_input(prompt_template={"name": "summary_es_v1"}))
        assert result.prompt_template.name == "summary_es_v1"

    def test_input_con_segments(self):
        data = _minimal_input(
            transcript_segments=[
                {"speaker": "audiologist", "start_ms": None, "end_ms": None, "text": "hola"}
            ]
        )
        result = input_from_dict(data)
        assert result.transcript_segments[0].speaker == "audiologist"


class TestReference:
    def test_reference_content_null_es_pendiente(self):
        result = reference_from_dict(
            {"artifact_type": "summary", "content": None},
            expected_artifact_type=AIArtifactType.SUMMARY,
        )
        assert result is None

    def test_reference_valida(self):
        result = reference_from_dict(
            {"artifact_type": "summary", "content": {"text": "resumen"}},
            expected_artifact_type=AIArtifactType.SUMMARY,
        )
        assert result.content == {"text": "resumen"}

    def test_reference_no_cumple_schema(self):
        with pytest.raises(ReferenceValidationError):
            reference_from_dict(
                {"artifact_type": "summary", "content": {"text": 5}},
                expected_artifact_type=AIArtifactType.SUMMARY,
            )

    def test_reference_artifact_type_no_coincide_con_input(self):
        with pytest.raises(ReferenceValidationError):
            reference_from_dict(
                {"artifact_type": "missing_information", "content": {"items": []}},
                expected_artifact_type=AIArtifactType.SUMMARY,
            )


class TestDatasetLoader:
    def test_caso_inexistente_lanza_error_tipado(self, tmp_path: Path):
        with pytest.raises(GenerationCaseNotFoundError):
            load_generation_case(tmp_path, "no_existe")

    def test_caso_sin_metadata_ni_reference_carga_igualmente(self, tmp_path: Path):
        case_dir = tmp_path / "caso_minimo"
        case_dir.mkdir()
        (case_dir / "input.json").write_text(
            json.dumps(_minimal_input(id="caso_minimo")), encoding="utf-8"
        )

        case = load_generation_case(tmp_path, "caso_minimo")

        assert case.reference is None
        assert case.metadata is None

    def test_list_generation_case_ids_directorio_inexistente(self, tmp_path: Path):
        assert list_generation_case_ids(tmp_path / "no_existe") == []

    def test_list_generation_case_ids_ignora_carpetas_sin_input(self, tmp_path: Path):
        (tmp_path / "vacia").mkdir()
        case_dir = tmp_path / "con_input"
        case_dir.mkdir()
        (case_dir / "input.json").write_text(
            json.dumps(_minimal_input(id="con_input")), encoding="utf-8"
        )

        assert list_generation_case_ids(tmp_path) == ["con_input"]

    # --- Los 3 casos reales del dataset (encargo Fase 6.2 §23) -------------

    @pytest.mark.parametrize(
        "case_id",
        [
            "consulta_ficticia_01__summary",
            "consulta_ficticia_01__missing_information",
            "consulta_ficticia_01__patient_summary",
        ],
    )
    def test_caso_real_carga_correctamente(self, case_id: str):
        case = load_generation_case(_REAL_DATASET_DIR, case_id)

        assert case.id == case_id
        assert case.input.transcript
        assert case.metadata is not None
        # Referencia humana aportada y validada (ver informe de la Fase 6.2).
        assert case.reference is not None
        assert case.reference.content is not None

    def test_los_3_casos_reales_listados(self):
        ids = list_generation_case_ids(_REAL_DATASET_DIR)
        assert set(ids) == {
            "consulta_ficticia_01__summary",
            "consulta_ficticia_01__missing_information",
            "consulta_ficticia_01__patient_summary",
        }
