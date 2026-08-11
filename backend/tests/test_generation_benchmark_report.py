"""Tests de `report.build_result`/`write_result` — Fase 6.2. Nunca
incluye API key, cabeceras ni el prompt completo (encargo §15)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.domain.validation_pipeline import ValidationOutcome
from benchmark.generation.gates import Finding, GateResult
from benchmark.generation.openrouter_client import LlmCompletionResponse
from benchmark.generation.report import build_result, write_result
from benchmark.generation.runner import GenerationBenchmarkOutcome, MetricsBundle

_TEMPLATE_ID = uuid.uuid4()


def _outcome(**overrides) -> GenerationBenchmarkOutcome:
    defaults = dict(
        case_id="consulta_ficticia_01__summary",
        artifact_type=AIArtifactType.SUMMARY,
        model="openai/gpt-test",
        ran_at="2026-08-11T10:00:00+00:00",
        latency_ms=1200,
        attempts=1,
        prompt_template_id=_TEMPLATE_ID,
        prompt_template_version=1,
        llm_response=LlmCompletionResponse(
            raw_text='{"text": "ok"}',
            model="openai/gpt-test",
            input_tokens=100,
            output_tokens=20,
            provider_reported_cost_usd=None,
        ),
        validation=ValidationOutcome(
            ok=True, content={"text": "ok"}, source_map=None, failure_reason=None
        ),
        metrics=MetricsBundle(
            required_facts=None,
            hallucination=None,
            negations=None,
            laterality=None,
            numeric=None,
            terminology=None,
            missing_information_completeness=None,
            evidence_coverage=None,
        ),
        gates=GateResult(
            safety_gate=True,
            hallucination_gate=None,
            schema_gate=True,
            negation_laterality_gate=None,
            passed_all=True,
            blocking_gate=None,
        ),
        findings=[],
        transport_error=None,
    )
    defaults.update(overrides)
    return GenerationBenchmarkOutcome(**defaults)


class TestBuildResult:
    def test_forma_minima_esperada(self):
        result = build_result(_outcome(), model_profile="openai__gpt-test")

        assert result["case_id"] == "consulta_ficticia_01__summary"
        assert result["artifact_type"] == "summary"
        assert result["model_profile"] == "openai__gpt-test"
        assert result["provider"] == "openrouter"
        assert result["prompt"] == {"template_id": str(_TEMPLATE_ID), "template_version": 1}
        assert result["execution"]["success"] is True
        assert result["execution"]["input_tokens"] == 100
        assert result["execution"]["output_tokens"] == 20
        assert result["output"] == {"text": "ok"}

    def test_nunca_incluye_secretos_ni_cabeceras(self):
        result = build_result(_outcome(), model_profile="openai__gpt-test")
        serialized = json.dumps(result)

        assert "Authorization" not in serialized
        assert "api_key" not in serialized
        assert "sk-" not in serialized

    def test_nunca_incluye_el_prompt_completo(self):
        result = build_result(_outcome(), model_profile="openai__gpt-test")
        serialized = json.dumps(result)

        # Solo metadata de plantilla (id/version), nunca el texto renderizado.
        assert "system_prompt" not in serialized
        assert "user_prompt" not in serialized

    def test_fallo_expone_failure_reason_y_no_output(self):
        outcome = _outcome(
            validation=ValidationOutcome(
                ok=False,
                content=None,
                source_map=None,
                failure_reason=AIGenerationFailureReason.SAFETY_POLICY_FAILED,
            ),
            gates=GateResult(
                safety_gate=False,
                hallucination_gate=None,
                schema_gate=True,
                negation_laterality_gate=None,
                passed_all=False,
                blocking_gate="safety",
            ),
            findings=[Finding("critical", "safety", "Lenguaje prohibido.")],
        )
        result = build_result(outcome, model_profile="openai__gpt-test")

        assert result["execution"]["success"] is False
        assert result["execution"]["failure_reason"] == "safety_policy_failed"
        assert result["output"] is None
        assert result["gates"]["passed_all"] is False
        assert result["findings"] == [
            {"severity": "critical", "category": "safety", "description": "Lenguaje prohibido."}
        ]

    def test_es_serializable_a_json_sin_errores(self):
        result = build_result(_outcome(), model_profile="openai__gpt-test")
        json.dumps(result)  # no debe lanzar


class TestWriteResult:
    def test_escribe_en_la_ruta_esperada(self, tmp_path: Path):
        result = build_result(_outcome(), model_profile="openai__gpt-test")

        output_path = write_result(
            result,
            results_dir=tmp_path,
            model_profile="openai__gpt-test",
            case_id="consulta_ficticia_01__summary",
        )

        assert output_path == tmp_path / "openai__gpt-test" / "consulta_ficticia_01__summary.json"
        assert json.loads(output_path.read_text(encoding="utf-8")) == result
