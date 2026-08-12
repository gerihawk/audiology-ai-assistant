"""Routing estático por artifact_type (Fase 6.3.7) — verifica que
`AIPipelineService._build_steps()` conecta el proveedor/modelo real
correcto para cada uno de los tres artifact_types, sin invocar nunca
`LanguageModelProvider.complete()` (cero red — eso lo cubre el hito
6.3.9 con HTTP simulado). Mismo patrón de `monkeypatch` sobre
`get_settings` que test_ai_pipeline_consent.py/test_ai_pipeline_cost_limit.py."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline import service as ai_pipeline_service_module
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.steps.missing_information_step import MissingInformationStep
from app.ai_pipeline.domain.steps.patient_summary_step import PatientSummaryStep
from app.ai_pipeline.domain.steps.summary_step import SummaryStep
from app.ai_pipeline.infrastructure.repository import SqlAlchemyPromptTemplateRepository
from app.ai_pipeline.prompts.catalog import seed_prompt_templates
from app.ai_pipeline.service import AIPipelineService
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.integrations.mocks.mock_summary_generator import MockSummaryGenerator
from app.integrations.providers.anthropic_language_model_provider import (
    AnthropicLanguageModelProvider,
)
from app.integrations.providers.google_language_model_provider import (
    GoogleLanguageModelProvider,
)
from app.integrations.providers.openai_language_model_provider import (
    OpenAILanguageModelProvider,
)
from app.integrations.providers.pricing_table_cost_estimator import PricingTableCostEstimator
from app.integrations.providers.real_missing_information_generator import (
    RealMissingInformationGenerator,
)
from app.integrations.providers.real_patient_summary_generator import (
    RealPatientSummaryGenerator,
)
from app.integrations.providers.real_summary_generator import RealSummaryGenerator
from tests.factories import ClinicWithUsers


def _settings(monkeypatch, **overrides) -> None:
    settings = get_settings().model_copy(update=overrides)
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)


async def _seed_templates(db_session: AsyncSession, clinic_with_users: ClinicWithUsers) -> None:
    await seed_prompt_templates(
        db_session, SqlAlchemyPromptTemplateRepository(), created_by=clinic_with_users.admin.id
    )
    await db_session.commit()


async def test_routing_mock_por_defecto_usa_el_generator_inyectado(db_session: AsyncSession):
    injected = MockSummaryGenerator()
    service = AIPipelineService(db_session, summary_generator=injected)

    steps = await service._build_steps()

    summary_step = next(s for s in steps if s.artifact_type == AIArtifactType.SUMMARY)
    assert isinstance(summary_step, SummaryStep)
    assert summary_step._generator is injected
    assert summary_step._provider_name == "mock"


async def test_routing_anthropic_construye_real_summary_generator(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    await _seed_templates(db_session, clinic_with_users)
    _settings(
        monkeypatch,
        llm_provider_summary="anthropic",
        llm_model_summary="claude-opus-5",
        anthropic_api_key="test-key",
    )
    service = AIPipelineService(db_session)

    steps = await service._build_steps()

    summary_step = next(s for s in steps if s.artifact_type == AIArtifactType.SUMMARY)
    assert isinstance(summary_step._generator, RealSummaryGenerator)
    assert isinstance(summary_step._generator._provider, AnthropicLanguageModelProvider)
    assert summary_step._provider_name == "anthropic"
    assert summary_step._model_name == "claude-opus-5"
    assert summary_step._prompt_template_id is not None
    assert summary_step._prompt_template_version == 1
    # CostEstimator real, no MockCostEstimator (nunca coste 0 artificial) —
    # ver Fase 6.3.8.
    assert isinstance(summary_step._cost_estimator, PricingTableCostEstimator)


async def test_routing_openai_construye_real_patient_summary_generator(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    await _seed_templates(db_session, clinic_with_users)
    _settings(
        monkeypatch,
        llm_provider_patient_summary="openai",
        llm_model_patient_summary="gpt-5.2",
        openai_api_key="test-key",
    )
    service = AIPipelineService(db_session)

    steps = await service._build_steps()

    step = next(s for s in steps if s.artifact_type == AIArtifactType.PATIENT_SUMMARY)
    assert isinstance(step, PatientSummaryStep)
    assert isinstance(step._generator, RealPatientSummaryGenerator)
    assert isinstance(step._generator._provider, OpenAILanguageModelProvider)
    assert step._provider_name == "openai"
    assert step._model_name == "gpt-5.2"


async def test_routing_google_construye_real_missing_information_generator(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    await _seed_templates(db_session, clinic_with_users)
    _settings(
        monkeypatch,
        llm_provider_missing_information="google",
        llm_model_missing_information="gemini-3.6-flash",
        google_api_key="test-key",
    )
    service = AIPipelineService(db_session)

    steps = await service._build_steps()

    step = next(s for s in steps if s.artifact_type == AIArtifactType.MISSING_INFORMATION)
    assert isinstance(step, MissingInformationStep)
    assert isinstance(step._generator, RealMissingInformationGenerator)
    assert isinstance(step._generator._provider, GoogleLanguageModelProvider)
    assert step._provider_name == "google"
    assert step._model_name == "gemini-3.6-flash"


async def test_routing_por_artifact_type_es_independiente(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    # SUMMARY -> google, PATIENT_SUMMARY -> openai, MISSING_INFORMATION ->
    # anthropic simultáneamente: cada uno resuelve su propio proveedor sin
    # interferir con los otros dos — nunca un único "proveedor activo"
    # global (RFC §11.1 decisión 12, "no existe global_winner").
    await _seed_templates(db_session, clinic_with_users)
    _settings(
        monkeypatch,
        llm_provider_summary="google",
        llm_model_summary="gemini-3.6-flash",
        google_api_key="g-key",
        llm_provider_patient_summary="openai",
        llm_model_patient_summary="gpt-5.2",
        openai_api_key="o-key",
        llm_provider_missing_information="anthropic",
        llm_model_missing_information="claude-opus-5",
        anthropic_api_key="a-key",
    )
    service = AIPipelineService(db_session)

    steps = await service._build_steps()
    by_type = {s.artifact_type: s for s in steps}

    assert isinstance(
        by_type[AIArtifactType.SUMMARY]._generator._provider, GoogleLanguageModelProvider
    )
    assert isinstance(
        by_type[AIArtifactType.PATIENT_SUMMARY]._generator._provider,
        OpenAILanguageModelProvider,
    )
    assert isinstance(
        by_type[AIArtifactType.MISSING_INFORMATION]._generator._provider,
        AnthropicLanguageModelProvider,
    )
    # ANAMNESIS/CLINICAL_FLAGS/TRANSCRIPT nunca se tocan por este routing.
    assert by_type[AIArtifactType.ANAMNESIS]._provider_name == "mock"


async def test_sin_modelo_configurado_falla_con_conflicterror_antes_de_construir_provider(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    await _seed_templates(db_session, clinic_with_users)
    _settings(
        monkeypatch, llm_provider_summary="anthropic", anthropic_api_key="test-key"
    )  # sin llm_model_summary
    service = AIPipelineService(db_session)

    try:
        await service._build_steps()
        raise AssertionError("Debía lanzar ConflictError")
    except ConflictError as exc:
        assert "LLM_MODEL_SUMMARY" in str(exc)


async def test_sin_plantilla_activa_falla_con_conflicterror_antes_de_construir_provider(
    db_session: AsyncSession, clinic_with_users: ClinicWithUsers, monkeypatch
):
    # Deliberadamente sin sembrar plantillas.
    _settings(
        monkeypatch,
        llm_provider_summary="anthropic",
        llm_model_summary="claude-opus-5",
        anthropic_api_key="test-key",
    )
    service = AIPipelineService(db_session)

    try:
        await service._build_steps()
        raise AssertionError("Debía lanzar ConflictError")
    except ConflictError as exc:
        assert "summary/es" in str(exc)
