"""Frontera mock/real entre los dos entrypoints del pipeline (corrección
de seguridad, ver docs/fase-6-rfc.md): `POST .../run-mock-pipeline` debe
ser estructuralmente incapaz de invocar un `LanguageModelProvider` real
sin importar cómo esté configurado `Settings`; `POST .../run-pipeline` sí
debe respetar el routing real, pasando antes por consentimiento y límite
de coste. Todo con `httpx.MockTransport` — cero red externa.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline import service as ai_pipeline_service_module
from app.ai_pipeline.infrastructure.orm import AIGenerationRunORM
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import seed_prompt_templates
from app.core.config import get_settings
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
from tests.factories import ClinicWithUsers, dev_headers

_ANTHROPIC_MODEL = "claude-opus-5"
_OPENAI_MODEL = "gpt-5.2"
_GOOGLE_MODEL = "gemini-3.6-flash"


def _real_provider_routing_settings(**overrides) -> dict:
    """Los tres artifact_types apuntando a un proveedor real — el mismo
    routing que se pretende usar en producción."""
    base = {
        "llm_provider_summary": "anthropic",
        "llm_model_summary": _ANTHROPIC_MODEL,
        "anthropic_api_key": "test-key",
        "llm_provider_patient_summary": "openai",
        "llm_model_patient_summary": _OPENAI_MODEL,
        "openai_api_key": "test-key",
        "llm_provider_missing_information": "google",
        "llm_model_missing_information": _GOOGLE_MODEL,
        "google_api_key": "test-key",
    }
    base.update(overrides)
    return base


def _never_call_handler(vendor: str):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"run-mock-pipeline nunca debía invocar a {vendor} — frontera mock/real violada."
        )

    return handler


def _mock_client(handler, *, base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)


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


def _patch_settings_and_providers(monkeypatch, *, settings_overrides: dict) -> None:
    """Monkeypatchea `get_settings` (rama de routing) y
    `build_language_model_provider` (los tres providers reales, con
    transporte simulado que revienta si se invoca) — igual que
    test_ai_pipeline_real_providers_integration.py, reutilizado aquí para
    demostrar que `run-mock-pipeline` NUNCA llega a ellos pese a que están
    completamente operativos y accesibles para `run-pipeline`."""
    providers_by_name = {
        "anthropic": AnthropicLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                _never_call_handler("Anthropic"), base_url="https://api.anthropic.com"
            ),
        ),
        "openai": OpenAILanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                _never_call_handler("OpenAI"), base_url="https://api.openai.com/v1"
            ),
        ),
        "google": GoogleLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                _never_call_handler("Google"),
                base_url="https://generativelanguage.googleapis.com",
            ),
        ),
    }
    settings = get_settings().model_copy(update=settings_overrides)
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        ai_pipeline_service_module,
        "build_language_model_provider",
        lambda settings, provider_name: providers_by_name[provider_name],
    )


async def test_run_mock_pipeline_con_routing_real_configurado_nunca_llama_a_un_provider_real(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Regresión de seguridad (encargo, punto 4): `run-mock-pipeline` +
    Settings reales configuradas -> cero llamadas a LanguageModelProvider
    real. Si `_build_mock_steps()` alguna vez empezara a consultar
    `Settings.llm_provider_*`, este test fallaría con el AssertionError
    del handler, no con una simple diferencia de datos."""
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()
    _patch_settings_and_providers(monkeypatch, settings_overrides=_real_provider_routing_settings())

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session['id']}/run-mock-pipeline", headers=headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"

    runs_result = await db_session.execute(
        select(AIGenerationRunORM).where(
            AIGenerationRunORM.ai_pipeline_run_id == uuid.UUID(body["pipeline_run_id"])
        )
    )
    runs = runs_result.scalars().all()
    assert len(runs) == 6
    # Los seis steps, incluidos los tres con routing real configurado,
    # se ejecutaron en Mock — nunca tocaron el provider real.
    assert all(run.provider_name == "mock" for run in runs)
    assert all(run.prompt_template_id is None for run in runs)


async def test_run_pipeline_configurado_si_usa_los_providers_reales_configurados(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Contraparte: el endpoint `run-pipeline` (configurado) sí debe
    alcanzar el provider real cuando el routing lo indica — aquí se deja
    que el transporte simulado devuelva éxito en vez de reventar, para
    demostrar el camino positivo end-to-end vía HTTP."""
    repository = SqlAlchemyPromptTemplateRepository()
    await seed_prompt_templates(db_session, repository, created_by=clinic_with_users.admin.id)
    await db_session.commit()

    def anthropic_success(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"text": "resumen real vía HTTP"}'}],
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    providers_by_name = {
        "anthropic": AnthropicLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(anthropic_success, base_url="https://api.anthropic.com"),
        ),
        "openai": OpenAILanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                lambda r: httpx.Response(
                    200,
                    json={
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": '{"text": "explicación"}'}
                                ],
                            }
                        ],
                        "usage": {"input_tokens": 8, "output_tokens": 3},
                    },
                ),
                base_url="https://api.openai.com/v1",
            ),
        ),
        "google": GoogleLanguageModelProvider(
            api_key="test-key",
            http_client=_mock_client(
                lambda r: httpx.Response(
                    200,
                    json={
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [{"type": "text", "text": '{"items": []}'}],
                            }
                        ],
                        "usage": {"total_input_tokens": 6, "total_output_tokens": 2},
                    },
                ),
                base_url="https://generativelanguage.googleapis.com",
            ),
        ),
    }
    settings = get_settings().model_copy(update=_real_provider_routing_settings())
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        ai_pipeline_service_module,
        "build_language_model_provider",
        lambda settings, provider_name: providers_by_name[provider_name],
    )

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session['id']}/run-pipeline", headers=headers
    )

    assert response.status_code == 201, response.text
    body = response.json()

    runs_result = await db_session.execute(
        select(AIGenerationRunORM).where(
            AIGenerationRunORM.ai_pipeline_run_id == uuid.UUID(body["pipeline_run_id"])
        )
    )
    runs_by_type = {run.artifact_type: run for run in runs_result.scalars().all()}
    assert runs_by_type["summary"].provider_name == "anthropic"
    assert runs_by_type["patient_summary"].provider_name == "openai"
    assert runs_by_type["missing_information"].provider_name == "google"
    # ANAMNESIS/CLINICAL_FLAGS siguen sin routing real en esta fase.
    assert runs_by_type["anamnesis"].provider_name == "mock"


async def test_run_pipeline_configurado_bloquea_sin_consentimiento_antes_de_llamar_al_provider(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()
    _patch_settings_and_providers(
        monkeypatch,
        settings_overrides=_real_provider_routing_settings(
            ai_processing_consent_enforced=True, ai_processing_consent_version="1.0"
        ),
    )

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session['id']}/run-pipeline", headers=headers
    )

    assert response.status_code == 409
    assert "consentimiento" in response.json()["error"]["message"].lower()


async def test_run_pipeline_configurado_bloquea_por_limite_de_coste_antes_de_llamar_al_provider(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()
    _patch_settings_and_providers(
        monkeypatch,
        settings_overrides=_real_provider_routing_settings(
            llm_cost_limit_enforced=True, max_llm_cost_per_session_usd=Decimal("0.000001")
        ),
    )

    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session['id']}/run-pipeline", headers=headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    summary_outcome = next(s for s in body["step_outcomes"] if s["artifact_type"] == "summary")
    assert summary_outcome["status"] == "failed"
    assert summary_outcome["failure_reason"] == "cost_limit_exceeded"
