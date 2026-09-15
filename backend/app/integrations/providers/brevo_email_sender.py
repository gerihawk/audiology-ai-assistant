"""BrevoEmailSender: EMAIL_PROVIDER=brevo (Fase 12, hito 12.1).

Usa exclusivamente la API REST oficial de Brevo (`POST /v3/smtp/email`) vía
`httpx` — sin SDK de terceros, mismo criterio que
`DeepgramTranscriptionProvider`/`AssemblyAITranscriptionProvider` (Fase 5).
Elegido en docs/fase-12-rfc.md §5 por ser empresa europea con hosting de
datos en Francia/Alemania — DPA autoservicio (Anexo 2 de sus Términos de
Servicio, entidad Sendinblue SAS para clientes de España), archivado en
docs/legal/brevo-dpa-2026-09-15.pdf. Nunca procesa datos de pacientes:
solo destinatarios de personal de clínica (verificación de registro,
recuperación de contraseña).

La API key nunca se registra en logs ni se incluye en ninguna excepción —
solo viaja en la cabecera `api-key` (ver CLAUDE.md, Secret handling).
"""

from __future__ import annotations

import httpx

from app.integrations.domain.email_sender import EmailMessage

_SEND_PATH = "/v3/smtp/email"


class BrevoEmailSender:
    def __init__(
        self,
        *,
        api_key: str | None,
        sender_email: str,
        sender_name: str,
        base_url: str = "https://api.brevo.com",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "BREVO_API_KEY es obligatoria para usar BrevoEmailSender (EMAIL_PROVIDER=brevo)."
            )
        self._api_key = api_key
        self._sender_email = sender_email
        self._sender_name = sender_name
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._injected_client = http_client

    async def send(self, message: EmailMessage) -> None:
        client = self._injected_client or httpx.AsyncClient(base_url=self._base_url)
        owns_client = self._injected_client is None
        try:
            response = await client.post(
                _SEND_PATH,
                headers=self._headers(),
                json={
                    "sender": {"name": self._sender_name, "email": self._sender_email},
                    "to": [{"email": message.to_email, "name": message.to_name}],
                    "subject": message.subject,
                    "htmlContent": message.html_body,
                    "textContent": message.text_body,
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        finally:
            if owns_client:
                await client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "api-key": self._api_key,
            "content-type": "application/json",
            "accept": "application/json",
        }
