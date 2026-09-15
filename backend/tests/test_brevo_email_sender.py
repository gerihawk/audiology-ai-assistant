"""Tests de BrevoEmailSender — Fase 12, hito 12.1.

`httpx.MockTransport` (parte de la propia librería httpx, sin dependencia
nueva) sustituye la red real — mismo criterio de "nunca llamar a un
proveedor de pago real en tests" que el resto del proyecto."""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.domain.email_sender import EmailMessage
from app.integrations.providers.brevo_email_sender import BrevoEmailSender

_MESSAGE = EmailMessage(
    to_email="destino@test.local",
    to_name="Destino",
    subject="Asunto de prueba",
    html_body="<p>Cuerpo HTML</p>",
    text_body="Cuerpo texto",
)


def test_brevo_email_sender_requires_api_key() -> None:
    with pytest.raises(ValueError):
        BrevoEmailSender(api_key=None, sender_email="a@b.com", sender_name="A")

    with pytest.raises(ValueError):
        BrevoEmailSender(api_key="", sender_email="a@b.com", sender_name="A")


async def test_send_posts_expected_payload_and_headers() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"messageId": "abc123"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.brevo.com"
    )
    sender = BrevoEmailSender(
        api_key="fake-api-key",
        sender_email="no-reply@audiology-assistant.dev",
        sender_name="Audiology AI Assistant",
        http_client=client,
    )

    await sender.send(_MESSAGE)

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/v3/smtp/email"
    assert request.headers["api-key"] == "fake-api-key"
    body = json.loads(request.content)
    assert body["sender"] == {
        "name": "Audiology AI Assistant",
        "email": "no-reply@audiology-assistant.dev",
    }
    assert body["to"] == [{"email": "destino@test.local", "name": "Destino"}]
    assert body["subject"] == "Asunto de prueba"
    assert body["htmlContent"] == "<p>Cuerpo HTML</p>"
    assert body["textContent"] == "Cuerpo texto"

    await client.aclose()


async def test_send_raises_on_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.brevo.com"
    )
    sender = BrevoEmailSender(
        api_key="clave-invalida",
        sender_email="no-reply@audiology-assistant.dev",
        sender_name="Audiology AI Assistant",
        http_client=client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await sender.send(_MESSAGE)

    await client.aclose()
