"""Regresión: el benchmark de generación (Fase 6.2) nunca cambia el
comportamiento de producción — encargo §24 ("producción sigue usando Mock
providers"). `PATIENT_SUMMARY` ya tiene `PipelineStep` registrado desde el
hito 6.3.1 — las dos pruebas que antes exigían su ausencia se invierten
aquí para exigir su presencia, sin perder cobertura de regresión."""

from __future__ import annotations

import inspect

import pytest

from app.ai_pipeline.domain.entities import PIPELINE_STEP_ORDER, AIArtifactType
from app.core.config import Settings
from benchmark.generation.cli import _require_enabled


def test_patient_summary_esta_en_el_orden_del_pipeline_productivo():
    # Hito 6.3.1: activado en producción con Mock — ver
    # docs/fase-6-rfc.md §10 hito 6.3.
    assert AIArtifactType.PATIENT_SUMMARY in PIPELINE_STEP_ORDER


def test_patient_summary_tiene_step_registrado_en_el_servicio():
    import app.ai_pipeline.service as service_module

    source = inspect.getsource(service_module)
    assert "AIArtifactType.PATIENT_SUMMARY:" in source


def test_app_arranca_sin_openrouter_api_key():
    # Ambos campos se fijan explícitamente — nunca se heredan de os.environ/
    # .env (pydantic-settings da prioridad a los kwargs del constructor sobre
    # el entorno real, que durante una ronda de benchmark sí tiene
    # GENERATION_BENCHMARK_ENABLED=true). El resultado de este test no debe
    # depender de qué .env se use para arrancar pytest.
    settings = Settings(openrouter_api_key=None, generation_benchmark_enabled=False)
    assert settings.openrouter_api_key is None
    assert settings.generation_benchmark_enabled is False


def test_benchmark_habilitado_sin_api_key_falla_de_forma_segura():
    # Contraparte del test anterior: benchmark habilitado pero sin API key
    # debe fallar ANTES de construir ningún cliente HTTP — sin llamada de
    # red y sin exponer secretos (aquí la key ya es None, así que no hay
    # nada que el mensaje de error pudiera filtrar).
    settings = Settings(generation_benchmark_enabled=True, openrouter_api_key=None)
    with pytest.raises(SystemExit) as exc_info:
        _require_enabled(settings)
    assert "OPENROUTER_API_KEY" in str(exc_info.value)


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
