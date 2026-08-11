"""Tests de `GenerationBenchmarkRunner` — Fase 6.2. DB real (para
`PromptTemplateRepository`), sin red: el `BenchmarkLLMClient` se sustituye
por un doble de test inyectado."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.core.config import Settings
from benchmark.generation.dataset import load_generation_case
from benchmark.generation.openrouter_client import (
    LlmCompletionResponse,
    OpenRouterTimeoutError,
)
from benchmark.generation.prompts import seed_prompt_templates
from benchmark.generation.runner import GenerationBenchmarkRunner, GenerationReferenceRequiredError
from tests.factories import ClinicWithUsers

_REAL_DATASET_DIR = Path(__file__).resolve().parent.parent / "benchmark" / "generation_dataset"


def _settings(**overrides) -> Settings:
    base = {
        "ai_pipeline_max_general_retries": 2,
        "ai_pipeline_max_regenerative_retries": 1,
        "ai_pipeline_retry_backoff_base_seconds": 0.0,
        "llm_max_output_tokens_estimate": 500,
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return Settings(**base)


class _FakeLlmClient:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list = []

    async def complete(self, request) -> LlmCompletionResponse:
        self.calls.append(request)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(
    text_content: str, *, input_tokens: int = 50, output_tokens: int = 10
) -> LlmCompletionResponse:
    return LlmCompletionResponse(
        raw_text=text_content,
        model="test/model",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_reported_cost_usd=None,
    )


async def _seed_and_load_case(db_session: AsyncSession, admin_id, case_id: str):
    repository = SqlAlchemyPromptTemplateRepository()
    await seed_prompt_templates(db_session, repository, created_by=admin_id)
    await db_session.commit()

    case = load_generation_case(_REAL_DATASET_DIR, case_id)
    # El caso real todavía no tiene reference.json relleno (encargo §23) —
    # se sustituye por una referencia válida mínima solo para estos tests
    # de infraestructura, que no evalúan contenido clínico real.
    from dataclasses import replace

    from benchmark.generation.reference import GenerationReference

    reference = GenerationReference(
        artifact_type=case.input.artifact_type,
        content={"text": "referencia de test"},
        notes=None,
    )
    return replace(case, reference=reference), repository


class TestReferenceRequirement:
    async def test_sin_referencia_no_invoca_al_modelo(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        repository = SqlAlchemyPromptTemplateRepository()
        await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)
        await db_session.commit()

        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__summary")
        assert case.reference is None  # confirma la precondición del test

        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=_FakeLlmClient([]),
        )
        with pytest.raises(GenerationReferenceRequiredError):
            await runner.run_one(case, model="test/model")


class TestSuccessPath:
    async def test_generacion_exitosa(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient([_response(json.dumps({"text": "Resumen válido."}))])
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is True
        assert outcome.attempts == 1
        assert outcome.validation.content == {"text": "Resumen válido."}
        assert outcome.prompt_template_id is not None
        assert len(client.calls) == 1

    async def test_generacion_exitosa_no_crea_ai_artifact(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient([_response(json.dumps({"text": "Resumen válido."}))])
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        await runner.run_one(case, model="test/model")

        result = await db_session.execute(text("SELECT COUNT(*) FROM ai_artifacts"))
        assert result.scalar_one() == 0
        result = await db_session.execute(text("SELECT COUNT(*) FROM ai_generation_runs"))
        assert result.scalar_one() == 0

    async def test_missing_information_no_requiere_transcript_como_variable(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        # Regresión del bug corregido: la plantilla de missing_information
        # no declara "transcript" — inyectarla incondicionalmente rompía
        # PromptRenderer con UnknownVariableError.
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__missing_information"
        )
        case.input.context["summary_text"] = "Resumen de prueba."
        case.input.context["clinical_flags_text"] = "Sin señales relevantes."
        client = _FakeLlmClient([_response(json.dumps({"items": []}))])
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is True


class TestRetries:
    async def test_json_malformado_reintenta_y_luego_tiene_exito(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient(
            [
                _response("esto no es JSON"),
                _response(json.dumps({"text": "Resumen válido tras corrección."})),
            ]
        )
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is True
        assert outcome.attempts == 2
        # El segundo intento incluye la nota de corrección, nunca datos
        # clínicos nuevos inventados por el runner.
        assert "Corrección" in client.calls[1].user_prompt

    async def test_json_malformado_agota_reintentos_y_falla(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient([_response("no-json")] * 3)
        runner = GenerationBenchmarkRunner(
            settings=_settings(ai_pipeline_max_general_retries=2),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is False
        assert outcome.attempts == 3
        assert (
            outcome.validation.failure_reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT
        )

    async def test_timeout_transitorio_reintenta(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient(
            [OpenRouterTimeoutError("timeout"), _response(json.dumps({"text": "ok tras timeout"}))]
        )
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is True
        assert outcome.attempts == 2

    async def test_cost_limit_exceeded_nunca_se_reintenta(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        # cost_limit_exceeded no forma parte de ningún grupo retryable de
        # retry_policy.py — 0 reintentos siempre, por diseño de producción.
        from app.ai_pipeline.domain.retry_policy import max_retries_for

        assert (
            max_retries_for(
                AIGenerationFailureReason.COST_LIMIT_EXCEEDED, max_general=2, max_regenerative=1
            )
            == 0
        )


class TestSafetyAndSchemaFailures:
    async def test_respuesta_evasiva_falla_sin_persistir_contenido(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        evasive = json.dumps({"text": "Soy una IA y no puedo generar contenido médico."})
        client = _FakeLlmClient([_response(evasive)] * 3)
        runner = GenerationBenchmarkRunner(
            settings=_settings(ai_pipeline_max_general_retries=2),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is False
        assert (
            outcome.validation.failure_reason == AIGenerationFailureReason.EVASIVE_OR_META_RESPONSE
        )
        assert outcome.validation.content is None

    async def test_lenguaje_clinico_prohibido_falla_safety_gate(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        forbidden = json.dumps({"text": "El paciente tiene una hipoacusia severa."})
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        client = _FakeLlmClient([_response(forbidden)] * 2)
        runner = GenerationBenchmarkRunner(
            settings=_settings(ai_pipeline_max_regenerative_retries=1),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is False
        assert outcome.validation.failure_reason == AIGenerationFailureReason.SAFETY_POLICY_FAILED
        assert outcome.gates.safety_gate is False
        assert outcome.gates.passed_all is False
        assert any(f.category == "safety" for f in outcome.findings)

    async def test_schema_invalido_falla_schema_gate(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        bad_schema = json.dumps({"resumen": "campo con nombre incorrecto"})
        client = _FakeLlmClient([_response(bad_schema)] * 3)
        runner = GenerationBenchmarkRunner(
            settings=_settings(ai_pipeline_max_general_retries=2),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is False
        assert (
            outcome.validation.failure_reason == AIGenerationFailureReason.SCHEMA_VALIDATION_FAILED
        )
        assert outcome.gates.schema_gate is False


class TestMetricsWiring:
    async def test_hallazgo_de_alucinacion_calculado_desde_metadata_real(
        self, db_session: AsyncSession, clinic_with_users: ClinicWithUsers
    ):
        case, repository = await _seed_and_load_case(
            db_session, clinic_with_users.admin.id, "consulta_ficticia_01__summary"
        )
        # metadata.json de este caso declara "vértigo" como forbidden_fact.
        assert case.metadata is not None
        assert any("vértigo" in fc.description for fc in case.metadata.forbidden_facts)

        hallucinated = json.dumps({"text": "El paciente refiere vértigo intenso y persistente."})
        client = _FakeLlmClient([_response(hallucinated)])
        runner = GenerationBenchmarkRunner(
            settings=_settings(),
            prompt_template_repository=repository,
            db_session=db_session,
            llm_client=client,
        )

        outcome = await runner.run_one(case, model="test/model")

        assert outcome.succeeded is True  # válido a nivel de schema/safety/grounding
        assert outcome.metrics.hallucination is not None
        assert outcome.metrics.hallucination.forbidden_found >= 1
        assert outcome.gates.passed_all is False
        assert outcome.gates.blocking_gate == "hallucination"
