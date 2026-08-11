"""Regresión: el benchmark de generación (Fase 6.2) nunca cambia el
comportamiento de producción — encargo §24 ("producción sigue usando Mock
providers") y precondición del hito ("PATIENT_SUMMARY sin PipelineStep
hasta el hito 6.3")."""

from __future__ import annotations

import inspect

from app.ai_pipeline.domain.entities import PIPELINE_STEP_ORDER, AIArtifactType
from app.core.config import Settings


def test_patient_summary_no_esta_en_el_orden_del_pipeline_productivo():
    assert AIArtifactType.PATIENT_SUMMARY not in PIPELINE_STEP_ORDER


def test_patient_summary_no_tiene_step_registrado_en_el_servicio():
    import app.ai_pipeline.service as service_module

    source = inspect.getsource(service_module)
    assert "AIArtifactType.PATIENT_SUMMARY:" not in source


def test_app_arranca_sin_openrouter_api_key():
    settings = Settings(openrouter_api_key=None)
    assert settings.openrouter_api_key is None
    assert settings.generation_benchmark_enabled is False


def test_openrouter_no_es_language_model_provider_productivo():
    import app.integrations.factory as factory_module

    source = inspect.getsource(factory_module)
    assert "openrouter" not in source.lower()


def test_benchmark_generation_nunca_importa_desde_app_ai_pipeline_service():
    # El runner reutiliza dominio puro (validation_pipeline, retry_policy,
    # prompt_renderer...) pero nunca AIPipelineService ni los repositorios
    # de AIArtifact — nunca puede terminar creando un artefacto clínico.
    import benchmark.generation.runner as runner_module

    source = inspect.getsource(runner_module)
    assert "AIPipelineService" not in source
    assert "AIArtifactRepository" not in source
