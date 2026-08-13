"""Tests de integración del pipeline completo usando el routing real por
`Settings` (Fase 6.3.7) contra los tres proveedores LLM reales COMO
CLASES, con transporte HTTP simulado (`httpx.MockTransport`) — cero red
externa (encargo Fase 6.3.9). Ejercita el camino de producción íntegro:
`AIPipelineService.run_pipeline` -> `_build_steps` (routing real) ->
`build_language_model_provider` (monkeypatcheado para devolver un
provider con transporte simulado, en vez de construir uno con red real)
-> `Real*Generator` -> `PromptTemplateRepository` real (BD) -> guardarraíles
existentes (safety/grounding/coste/reintentos) -> persistencia/auditoría.

`SUMMARY` → Anthropic, `PATIENT_SUMMARY` → OpenAI, `MISSING_INFORMATION` →
Google — routing usado aquí solo para ejercitar los tres adapters a la
vez; no implica que estos sean los ganadores reales de producción (eso lo
decide el usuario).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline import service as ai_pipeline_service_module
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.domain.errors import AIGenerationFailureReason
from app.ai_pipeline.infrastructure.orm import AIGenerationRunORM
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import seed_prompt_templates
from app.ai_pipeline.service import AIPipelineService
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.integrations.providers.anthropic_language_model_provider import (
    AnthropicLanguageModelProvider,
)
from app.integrations.providers.google_language_model_provider import (
    GoogleLanguageModelProvider,
)
from app.integrations.providers.openai_language_model_provider import (
    OpenAILanguageModelProvider,
)
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, current_user_from, dev_headers

_ANTHROPIC_MODEL = "claude-opus-5"
_OPENAI_MODEL = "gpt-5.2"
_GOOGLE_MODEL = "gemini-3.6-flash"


def _mock_client(handler, *, base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)


def _anthropic_success(text: str, *, input_tokens=40, output_tokens=10):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            },
        )

    return handler


def _openai_success(text: str, *, input_tokens=25, output_tokens=6):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            },
        )

    return handler


def _google_success(text: str, *, input_tokens=18, output_tokens=5):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
                "usage": {
                    "total_input_tokens": input_tokens,
                    "total_output_tokens": output_tokens,
                },
            },
        )

    return handler


async def _create_session(
    api_client: AsyncClient, headers: dict[str, str], patient_id: str, professional_id: str
) -> dict:
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": patient_id,
            "professional_id": professional_id,
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _build_service(
    monkeypatch,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    *,
    anthropic_handler=None,
    openai_handler=None,
    google_handler=None,
    settings_overrides: dict | None = None,
) -> AIPipelineService:
    """Siembra las plantillas reales (BD, `PromptTemplateRepository`
    activo), activa el routing real por `Settings` para los tres
    artifact_types (mismo mecanismo que Fase 6.3.7) y sustituye
    `build_language_model_provider` para que devuelva providers reales con
    transporte HTTP simulado en vez de construir uno con red real — el
    resto del camino de producción (`_build_steps`, guardarraíles,
    persistencia) se ejecuta sin ningún atajo de test."""
    repository = SqlAlchemyPromptTemplateRepository()
    await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)
    await db_session.commit()

    providers_by_name = {
        "anthropic": AnthropicLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                anthropic_handler or _anthropic_success('{"text": "resumen técnico"}'),
                base_url="https://api.anthropic.com",
            ),
        ),
        "openai": OpenAILanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                openai_handler or _openai_success('{"text": "explicación para el paciente"}'),
                base_url="https://api.openai.com/v1",
            ),
        ),
        "google": GoogleLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                google_handler
                or _google_success(
                    '{"items": [{"topic": "antecedentes_familiares", '
                    '"suggested_question": "¿Hay antecedentes familiares?"}]}'
                ),
                base_url="https://generativelanguage.googleapis.com",
            ),
        ),
    }

    settings = get_settings().model_copy(
        update={
            "llm_provider_summary": "anthropic",
            "llm_model_summary": _ANTHROPIC_MODEL,
            "anthropic_api_key": "test-key",
            "llm_provider_patient_summary": "openai",
            "llm_model_patient_summary": _OPENAI_MODEL,
            "openai_api_key": "test-key",
            "llm_provider_missing_information": "google",
            "llm_model_missing_information": _GOOGLE_MODEL,
            "google_api_key": "test-key",
            **(settings_overrides or {}),
        }
    )
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        ai_pipeline_service_module,
        "build_language_model_provider",
        lambda settings, provider_name: providers_by_name[provider_name],
    )

    return AIPipelineService(db_session)


def _outcome_for(outcomes, artifact_type: AIArtifactType):
    return next(o for o in outcomes if o.artifact_type == artifact_type)


async def test_pipeline_completo_con_los_tres_providers_reales(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(monkeypatch, db_session, clinic_with_users)
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-1")

    assert result.pipeline_run.status.value == "completed"

    summary = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary.status == AIGenerationRunStatus.COMPLETED

    runs_result = await db_session.execute(
        select(AIGenerationRunORM).where(
            AIGenerationRunORM.ai_pipeline_run_id == result.pipeline_run.id
        )
    )
    runs_by_type = {row.artifact_type: row for row in runs_result.scalars().all()}

    summary_run = runs_by_type["summary"]
    assert summary_run.provider_name == "anthropic"
    assert summary_run.model_name == _ANTHROPIC_MODEL
    assert summary_run.prompt_template_id is not None
    assert summary_run.input_token_count == 40
    assert summary_run.output_token_count == 10
    assert summary_run.estimated_cost_usd > Decimal("0")

    patient_summary_run = runs_by_type["patient_summary"]
    assert patient_summary_run.provider_name == "openai"
    assert patient_summary_run.model_name == _OPENAI_MODEL
    assert patient_summary_run.prompt_template_id is not None

    missing_info_run = runs_by_type["missing_information"]
    assert missing_info_run.provider_name == "google"
    assert missing_info_run.model_name == _GOOGLE_MODEL
    assert missing_info_run.prompt_template_id is not None

    # ANAMNESIS sigue Mock (hito 6.4, no esta fase) y CLINICAL_FLAGS sigue
    # basado en reglas — ninguno de los dos toca un LanguageModelProvider.
    assert runs_by_type["anamnesis"].provider_name == "mock"
    assert runs_by_type["clinical_flags"].provider_name == "mock"
    assert runs_by_type["clinical_flags"].model_name is None


async def test_timeout_en_summary_falla_tipado_y_bloquea_missing_information_en_cascada(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("tiempo agotado (fixture de test)")

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch, db_session, clinic_with_users, anthropic_handler=timeout_handler
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-timeout")

    summary = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary.status == AIGenerationRunStatus.FAILED
    assert summary.failure_reason == AIGenerationFailureReason.PROVIDER_TIMEOUT.value

    missing_info = _outcome_for(result.outcomes, AIArtifactType.MISSING_INFORMATION)
    assert missing_info.status is None  # saltado en cascada, nunca invocado
    assert missing_info.skipped_reason is not None

    patient_summary = _outcome_for(result.outcomes, AIArtifactType.PATIENT_SUMMARY)
    assert patient_summary.status == AIGenerationRunStatus.COMPLETED  # solo depende de TRANSCRIPT

    assert result.pipeline_run.status.value == "partially_failed"


async def test_429_en_summary_se_reintenta_segun_la_politica_existente(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    attempts = 0

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"text": "resumen tras reintento"}'}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch,
        db_session,
        clinic_with_users,
        anthropic_handler=flaky_handler,
        settings_overrides={"ai_pipeline_retry_backoff_base_seconds": 0.0},
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-retry")

    summary = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary.status == AIGenerationRunStatus.COMPLETED
    assert attempts == 2  # intento inicial (429) + 1 reintento con éxito


async def test_5xx_en_patient_summary_falla_provider_unavailable(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch, db_session, clinic_with_users, openai_handler=handler
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-5xx")

    patient_summary = _outcome_for(result.outcomes, AIArtifactType.PATIENT_SUMMARY)
    assert patient_summary.status == AIGenerationRunStatus.FAILED
    assert patient_summary.failure_reason == AIGenerationFailureReason.PROVIDER_UNAVAILABLE.value


async def test_json_malformado_en_missing_information_falla_invalid_response_format(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "esto no es JSON válido"}],
                    }
                ],
                "usage": {"total_input_tokens": 10, "total_output_tokens": 5},
            },
        )

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch, db_session, clinic_with_users, google_handler=handler
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(
        current_user, uuid.UUID(session["id"]), "req-real-malformed"
    )

    missing_info = _outcome_for(result.outcomes, AIArtifactType.MISSING_INFORMATION)
    assert missing_info.status == AIGenerationRunStatus.FAILED
    assert missing_info.failure_reason == AIGenerationFailureReason.INVALID_RESPONSE_FORMAT.value


async def test_lenguaje_prohibido_en_summary_falla_safety_policy(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    handler = _anthropic_success('{"text": "el paciente tiene una posible pérdida auditiva"}')

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch, db_session, clinic_with_users, anthropic_handler=handler
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-safety")

    summary = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary.status == AIGenerationRunStatus.FAILED
    assert summary.failure_reason == AIGenerationFailureReason.SAFETY_POLICY_FAILED.value


async def test_consentimiento_bloqueante_impide_invocar_al_proveedor_real(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Nunca debía invocarse el proveedor sin consentimiento")

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch,
        db_session,
        clinic_with_users,
        anthropic_handler=handler,
        settings_overrides={
            "ai_processing_consent_enforced": True,
            "ai_processing_consent_version": "1.0",
        },
    )
    current_user = current_user_from(clinic_with_users.admin)

    try:
        await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-real-consent")
        raise AssertionError("Debía lanzar ConflictError por falta de consentimiento")
    except ConflictError:
        pass
    assert calls == 0


async def test_limite_de_coste_bloquea_antes_de_invocar_al_proveedor_real(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Nunca debía invocarse el proveedor por encima del límite")

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    service = await _build_service(
        monkeypatch,
        db_session,
        clinic_with_users,
        anthropic_handler=handler,
        settings_overrides={
            "llm_cost_limit_enforced": True,
            "max_llm_cost_per_session_usd": Decimal("0.000001"),
        },
    )
    current_user = current_user_from(clinic_with_users.admin)

    result = await service.run_pipeline(
        current_user, uuid.UUID(session["id"]), "req-real-costlimit"
    )

    summary = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary.status == AIGenerationRunStatus.FAILED
    assert summary.failure_reason == AIGenerationFailureReason.COST_LIMIT_EXCEEDED.value
    assert calls == 0
