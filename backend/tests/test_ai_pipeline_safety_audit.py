"""Tests del Paso 2 del cierre del hallazgo bloqueante del red team
(docs/security/red-team-app-2026-09-22.md §A1): capa de auditoría LLM no
bloqueante. Cobertura pedida explícitamente: el mock, que un fallo del
proveedor no bloquea ni falla nada, y que la llamada nunca ocurre si
`LLM_PROVIDER_SAFETY_AUDIT` está inactivo (valor por defecto)."""

from __future__ import annotations

import json
import uuid

import pytest

from app.ai_pipeline.domain.safety_audit import (
    PROMPT_VERSION,
    build_safety_audit_prompt,
    parse_safety_audit_response,
)
from app.ai_pipeline.safety_audit_task import run_safety_audit
from app.core.config import get_settings
from app.integrations.domain.language_model_provider import LanguageModelResponse, RenderedPrompt
from app.integrations.factory import build_safety_audit_provider
from app.integrations.mocks.mock_safety_audit_provider import MockSafetyAuditProvider


class _RaisingProvider:
    async def complete(self, prompt, *, model=None, response_json_schema=None):
        raise TimeoutError("proveedor caído (simulado)")


class _FixedProvider:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, prompt, *, model=None, response_json_schema=None):
        return LanguageModelResponse(text=json.dumps(self._payload, ensure_ascii=False))


class _SpyRepository:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def add(self, session, **kwargs):
        self.calls.append(kwargs)


class _FakeSession:
    async def commit(self):
        pass


class _FakeSessionCM:
    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, *exc_info):
        return False


def _should_not_be_called(*_args, **_kwargs):
    raise AssertionError("no debería invocarse en este escenario")


# --- MockSafetyAuditProvider ------------------------------------------------


async def test_mock_provider_flagged_false_por_defecto():
    provider = MockSafetyAuditProvider()
    response = await provider.complete(RenderedPrompt(system="s", user="u"))
    verdict = parse_safety_audit_response(response.text)
    assert verdict.flagged is False
    assert verdict.field is None


async def test_mock_provider_configurable_a_flagged_true():
    provider = MockSafetyAuditProvider(
        flagged=True, reasoning="Presenta un diagnóstico como hecho.", field="summary"
    )
    response = await provider.complete(RenderedPrompt(system="s", user="u"))
    verdict = parse_safety_audit_response(response.text)
    assert verdict.flagged is True
    assert verdict.field == "summary"
    assert verdict.reasoning == "Presenta un diagnóstico como hecho."


# --- prompt/parseo puros -----------------------------------------------------


def test_build_safety_audit_prompt_incluye_cada_artifact_type():
    prompt = build_safety_audit_prompt({"summary": "texto A", "anamnesis": "texto B"})
    assert "summary" in prompt.user
    assert "texto A" in prompt.user
    assert "anamnesis" in prompt.user
    assert "texto B" in prompt.user


def test_parse_safety_audit_response_forma_invalida_lanza():
    with pytest.raises(ValueError):
        parse_safety_audit_response(json.dumps({"flagged": "no-es-bool", "reasoning": "x"}))


# --- build_safety_audit_provider: off por defecto ---------------------------


def test_build_safety_audit_provider_off_por_defecto():
    settings = get_settings()
    assert settings.llm_provider_safety_audit == "off"
    assert build_safety_audit_provider(settings) is None


def test_build_safety_audit_provider_mock():
    settings = get_settings().model_copy(update={"llm_provider_safety_audit": "mock"})
    provider = build_safety_audit_provider(settings)
    assert isinstance(provider, MockSafetyAuditProvider)


# --- run_safety_audit: orquestación -----------------------------------------


async def test_run_safety_audit_no_hace_nada_si_esta_off():
    settings = get_settings().model_copy(update={"llm_provider_safety_audit": "off"})
    # Si "off" no cortocircuitara antes de nada, cualquiera de estos dos
    # stubs lanzaría AssertionError.
    await run_safety_audit(
        uuid.uuid4(),
        {"summary": (uuid.uuid4(), "texto")},
        settings=settings,
        repository=type("R", (), {"add": staticmethod(_should_not_be_called)})(),
        session_factory=_should_not_be_called,
    )


async def test_run_safety_audit_mapa_vacio_no_hace_nada():
    await run_safety_audit(
        uuid.uuid4(),
        {},
        session_factory=_should_not_be_called,
    )


async def test_run_safety_audit_fallo_del_proveedor_no_bloquea_ni_propaga():
    # No debe lanzar, y no debe intentar escribir nada tras el fallo.
    await run_safety_audit(
        uuid.uuid4(),
        {"summary": (uuid.uuid4(), "texto")},
        provider=_RaisingProvider(),
        session_factory=_should_not_be_called,
    )


async def test_run_safety_audit_flagged_false_no_escribe_nada():
    repository = _SpyRepository()
    await run_safety_audit(
        uuid.uuid4(),
        {"summary": (uuid.uuid4(), "texto")},
        provider=_FixedProvider({"flagged": False, "reasoning": "sin hallazgos", "field": None}),
        repository=repository,
        session_factory=lambda: _FakeSessionCM(),
    )
    assert repository.calls == []


async def test_run_safety_audit_flagged_true_sin_field_escribe_todos_los_artefactos():
    clinic_id = uuid.uuid4()
    version_summary = uuid.uuid4()
    version_anamnesis = uuid.uuid4()
    repository = _SpyRepository()
    await run_safety_audit(
        clinic_id,
        {
            "summary": (version_summary, "texto A"),
            "anamnesis": (version_anamnesis, "texto B"),
        },
        provider=_FixedProvider(
            {"flagged": True, "reasoning": "Presenta un diagnóstico como hecho.", "field": None}
        ),
        repository=repository,
        session_factory=lambda: _FakeSessionCM(),
    )
    assert len(repository.calls) == 2
    written_version_ids = {call["ai_artifact_version_id"] for call in repository.calls}
    assert written_version_ids == {version_summary, version_anamnesis}
    for call in repository.calls:
        assert call["clinic_id"] == clinic_id
        assert call["llm_flagged"] is True
        assert call["prompt_version"] == PROMPT_VERSION
        # Nunca el texto completo — solo el motivo corto del modelo.
        assert call["llm_reasoning"] == "Presenta un diagnóstico como hecho."
        assert "texto A" not in call["llm_reasoning"]
        assert "texto B" not in call["llm_reasoning"]


async def test_run_safety_audit_flagged_true_con_field_escribe_solo_ese_artefacto():
    version_summary = uuid.uuid4()
    version_anamnesis = uuid.uuid4()
    repository = _SpyRepository()
    await run_safety_audit(
        uuid.uuid4(),
        {
            "summary": (version_summary, "texto A"),
            "anamnesis": (version_anamnesis, "texto B"),
        },
        provider=_FixedProvider(
            {
                "flagged": True,
                "reasoning": "Solo el resumen presenta el problema.",
                "field": "summary",
            }
        ),
        repository=repository,
        session_factory=lambda: _FakeSessionCM(),
    )
    assert len(repository.calls) == 1
    assert repository.calls[0]["ai_artifact_version_id"] == version_summary
