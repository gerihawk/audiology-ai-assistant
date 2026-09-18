"""Tests de `is_disposable_email_domain` — Fase 12, hito 12.4 ampliado
(2026-09-18), ver app/onboarding/domain/disposable_email_domains.py."""

from __future__ import annotations

from app.onboarding.domain.disposable_email_domains import is_disposable_email_domain


def test_known_disposable_domain_is_flagged() -> None:
    assert is_disposable_email_domain("alguien@mailinator.com") is True


def test_known_disposable_domain_is_flagged_case_insensitively() -> None:
    assert is_disposable_email_domain("Alguien@Mailinator.COM") is True


def test_ordinary_domain_is_not_flagged() -> None:
    assert is_disposable_email_domain("gerard@gmail.com") is False


def test_clinic_style_domain_is_not_flagged() -> None:
    assert is_disposable_email_domain("admin@clinica-auditiva.es") is False


def test_similar_but_different_domain_is_not_falsely_flagged() -> None:
    """No debe hacer coincidencia parcial: un dominio real que solo
    contiene la cadena de uno bloqueado no debe caer en el bloqueo."""
    assert is_disposable_email_domain("alguien@notmailinator.com") is False
