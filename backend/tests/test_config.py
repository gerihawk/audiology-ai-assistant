from decimal import Decimal

import pytest

from app.core.config import Settings


def _base_kwargs(**overrides: str) -> dict:
    kwargs = {
        "postgres_user": "user",
        "postgres_password": "s3cret",
        "postgres_db": "db",
        "postgres_host": "localhost",
        "backend_cors_origins": "https://app.example.com",
        # Fase 9, hito 9.1: baseline válida de production también para
        # AUTH_MODE/JWT_SECRET_KEY — cada test "rejects" de más abajo
        # sobreescribe únicamente el campo que está probando.
        "auth_mode": "real",
        "jwt_secret_key": "s3cret-enough-for-jwt-at-least-32-bytes",
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


def test_production_rejects_fake_auth_mode() -> None:
    with pytest.raises(ValueError, match="AUTH_MODE"):
        Settings(
            environment="production",
            **{**_base_kwargs(), "auth_mode": "fake"},
        )


def test_production_rejects_insecure_default_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            environment="production",
            **{**_base_kwargs(), "jwt_secret_key": "CHANGE_ME_LOCAL_ONLY"},
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


# --- env_ignore_empty (docker-compose.yml usa `${VAR:-}`) ----------------
#
# `docker-compose.yml` pasa variables opcionales no configuradas por el
# usuario como cadena vacía (fallback `${VAR:-}`). Sin `env_ignore_empty`,
# pydantic-settings trata esa cadena vacía como un valor explícito e
# inválido para campos no-str (bool/Decimal/Literal), y `Settings()` lanza
# `ValidationError` en lugar de aplicar el default de Python. Estos tests
# construyen `Settings` leyendo variables de entorno reales (vía
# monkeypatch), nunca pasándolas como kwarg, para probar el comportamiento
# de carga desde entorno — no solo la validación de kwargs explícitos.


def test_env_ignore_empty_variable_vacia_opcional_se_trata_como_no_definida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_COST_LIMIT_ENFORCED", "")
    monkeypatch.setenv("MAX_LLM_COST_PER_SESSION_USD", "")
    monkeypatch.setenv("AI_PROCESSING_CONSENT_ENFORCED", "")
    monkeypatch.setenv("LLM_PROVIDER_SUMMARY", "")
    # No lanza ValidationError: la cadena vacía se ignora, no se valida
    # como bool/Decimal/Literal inválido.
    settings = Settings(**_base_kwargs())
    # Test de "default aplicado correctamente": cae al default de Python
    # de cada campo, exactamente igual que si la variable no existiera.
    assert settings.llm_cost_limit_enforced is False
    assert settings.max_llm_cost_per_session_usd is None
    assert settings.ai_processing_consent_enforced is False
    assert settings.llm_provider_summary == "mock"


# --- Gating de /docs, /redoc, /openapi.json en production (Fase 10.5) ----


def test_docs_kwargs_deshabilitados_en_production() -> None:
    from app.main import _docs_kwargs_for

    settings = Settings(environment="production", **_base_kwargs())
    assert _docs_kwargs_for(settings) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_docs_kwargs_disponibles_en_development() -> None:
    from app.main import _docs_kwargs_for

    settings = Settings(environment="development", **_base_kwargs())
    assert _docs_kwargs_for(settings) == {}


def test_env_ignore_empty_valor_real_presente_sigue_parseandose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_COST_LIMIT_ENFORCED", "true")
    monkeypatch.setenv("MAX_LLM_COST_PER_SESSION_USD", "0.05")
    monkeypatch.setenv("AI_PROCESSING_CONSENT_ENFORCED", "true")
    monkeypatch.setenv("LLM_PROVIDER_SUMMARY", "google")
    settings = Settings(**_base_kwargs())
    assert settings.llm_cost_limit_enforced is True
    assert settings.max_llm_cost_per_session_usd == Decimal("0.05")
    assert settings.ai_processing_consent_enforced is True
    assert settings.llm_provider_summary == "google"
