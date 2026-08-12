import pytest

from app.core.config import Settings


def _base_kwargs(**overrides: str) -> dict:
    kwargs = {
        "postgres_user": "user",
        "postgres_password": "s3cret",
        "postgres_db": "db",
        "postgres_host": "localhost",
        "backend_cors_origins": "https://app.example.com",
    }
    kwargs.update(overrides)
    return kwargs


def test_development_allows_wildcard_cors() -> None:
    settings = Settings(
        environment="development",
        backend_cors_origins="*",
        **{k: v for k, v in _base_kwargs().items() if k != "backend_cors_origins"},
    )
    assert settings.cors_origins == ["*"]


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="BACKEND_CORS_ORIGINS"):
        Settings(
            environment="production",
            **{
                **_base_kwargs(),
                "backend_cors_origins": "*",
            },
        )


def test_production_rejects_insecure_default_password() -> None:
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(
            environment="production",
            **{
                **_base_kwargs(),
                "postgres_password": "CHANGE_ME_LOCAL_ONLY",
            },
        )


def test_production_accepts_valid_configuration() -> None:
    settings = Settings(environment="production", **_base_kwargs())
    assert settings.is_production is True
    assert settings.cors_origins == ["https://app.example.com"]


# --- Routing LLM por artifact_type (Fase 6.3.4) --------------------------


def test_routing_llm_por_defecto_es_mock_en_los_tres_artifact_types() -> None:
    settings = Settings(**_base_kwargs())
    assert settings.llm_provider_summary == "mock"
    assert settings.llm_provider_patient_summary == "mock"
    assert settings.llm_provider_missing_information == "mock"


def test_production_con_todo_mock_no_exige_ningun_guardarrail_llm() -> None:
    settings = Settings(environment="production", **_base_kwargs())
    assert settings.llm_cost_limit_enforced is False
    assert settings.ai_processing_consent_enforced is False


def test_production_con_proveedor_real_exige_consentimiento_activo() -> None:
    with pytest.raises(ValueError, match="AI_PROCESSING_CONSENT_ENFORCED"):
        Settings(
            environment="production",
            llm_provider_summary="google",
            **_base_kwargs(),
        )


def test_production_con_proveedor_real_exige_limite_de_coste_activo() -> None:
    with pytest.raises(ValueError, match="LLM_COST_LIMIT_ENFORCED"):
        Settings(
            environment="production",
            llm_provider_summary="google",
            ai_processing_consent_enforced=True,
            **_base_kwargs(),
        )


def test_production_con_proveedor_real_exige_max_cost_positivo() -> None:
    with pytest.raises(ValueError, match="MAX_LLM_COST_PER_SESSION_USD"):
        Settings(
            environment="production",
            llm_provider_summary="google",
            ai_processing_consent_enforced=True,
            llm_cost_limit_enforced=True,
            **_base_kwargs(),
        )


def test_production_con_proveedor_real_exige_api_key_del_vendor_activo() -> None:
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        Settings(
            environment="production",
            llm_provider_summary="google",
            ai_processing_consent_enforced=True,
            llm_cost_limit_enforced=True,
            max_llm_cost_per_session_usd="10.00",
            **_base_kwargs(),
        )


def test_production_con_proveedor_real_y_configuracion_completa_es_valida() -> None:
    settings = Settings(
        environment="production",
        llm_provider_summary="google",
        google_api_key="test-key",
        ai_processing_consent_enforced=True,
        llm_cost_limit_enforced=True,
        max_llm_cost_per_session_usd="10.00",
        **_base_kwargs(),
    )
    assert settings.llm_provider_summary == "google"


def test_production_solo_exige_key_del_vendor_realmente_usado() -> None:
    # Dos artifact_types en el mismo vendor solo exigen una key, nunca
    # duplicada — y no exige keys de vendors que ningún artifact_type usa.
    settings = Settings(
        environment="production",
        llm_provider_summary="anthropic",
        llm_provider_missing_information="anthropic",
        anthropic_api_key="test-key",
        ai_processing_consent_enforced=True,
        llm_cost_limit_enforced=True,
        max_llm_cost_per_session_usd="10.00",
        **_base_kwargs(),
    )
    assert settings.openai_api_key is None
    assert settings.google_api_key is None


def test_development_con_proveedor_real_configurado_nunca_bloquea() -> None:
    # Development/test siguen funcionando solo con Mock y sin claves
    # reales — activar un provider real en development no está prohibido,
    # simplemente no se valida (la app seguiría usando Mock salvo que el
    # propio código de arranque decida lo contrario).
    settings = Settings(environment="development", llm_provider_summary="openai", **_base_kwargs())
    assert settings.llm_provider_summary == "openai"
    assert settings.openai_api_key is None
