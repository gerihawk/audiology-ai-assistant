"""Tests de CloudflareTurnstileVerifier — Fase 12, hito 12.4 ampliado
(2026-09-18).

`httpx.MockTransport` sustituye la red real — mismo criterio que
test_brevo_email_sender.py: nunca llamar a un proveedor externo real en
tests."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.providers.cloudflare_turnstile_verifier import (
    CloudflareTurnstileVerifier,
)


def test_requires_secret_key() -> None:
    with pytest.raises(ValueError):
        CloudflareTurnstileVerifier(secret_key=None)

    with pytest.raises(ValueError):
        CloudflareTurnstileVerifier(secret_key="")


async def test_verify_posts_token_and_remote_ip_and_returns_true_on_success() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"success": True})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://challenges.cloudflare.com",
    )
    verifier = CloudflareTurnstileVerifier(secret_key="fake-secret", http_client=client)

    result = await verifier.verify("token-del-widget", remote_ip="203.0.113.7")

    assert result is True
    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/turnstile/v0/siteverify"
    body = dict(pair.split("=") for pair in request.content.decode().split("&"))
    assert body["secret"] == "fake-secret"
    assert body["response"] == "token-del-widget"
    assert body["remoteip"] == "203.0.113.7"

    await client.aclose()


async def test_verify_returns_false_when_cloudflare_rejects_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "error-codes": ["invalid-input-response"]}
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://challenges.cloudflare.com",
    )
    verifier = CloudflareTurnstileVerifier(secret_key="fake-secret", http_client=client)

    result = await verifier.verify("token-invalido", remote_ip=None)

    assert result is False
    await client.aclose()


async def test_verify_returns_false_on_empty_token_without_calling_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería llamar a Cloudflare con un token vacío")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://challenges.cloudflare.com",
    )
    verifier = CloudflareTurnstileVerifier(secret_key="fake-secret", http_client=client)

    result = await verifier.verify("", remote_ip=None)

    assert result is False
    await client.aclose()


async def test_verify_returns_false_on_transport_failure_instead_of_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://challenges.cloudflare.com",
    )
    verifier = CloudflareTurnstileVerifier(secret_key="fake-secret", http_client=client)

    result = await verifier.verify("token-cualquiera", remote_ip=None)

    assert result is False
    await client.aclose()
