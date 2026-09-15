"""ConsoleEmailSender: EMAIL_PROVIDER=mock (por defecto) — sin envío real.

Mismo espíritu que `MockTranscriptionProvider`: nunca contacta un
proveedor de pago. En vez de descartar el mensaje en silencio, lo registra
a nivel INFO — así, en desarrollo local, el enlace de verificación/reseteo
(dentro de `html_body`/`text_body`) queda disponible en
`docker compose logs backend` sin necesidad de credenciales reales de
Brevo. Nunca usar en production (ver `Settings`, sin guardarraíl propio
todavía — la elección de proveedor en production es una decisión
operativa de Gerard, igual que `TRANSCRIPTION_PROVIDER`, no forzada por
`_validate_production_safety`).
"""

from __future__ import annotations

import logging

from app.integrations.domain.email_sender import EmailMessage

logger = logging.getLogger("app.integrations.email.mock")


class ConsoleEmailSender:
    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "Email simulado (EMAIL_PROVIDER=mock) — nunca enviado de verdad",
            extra={
                "context": {
                    "to_email": message.to_email,
                    "to_name": message.to_name,
                    "subject": message.subject,
                    "text_body": message.text_body,
                }
            },
        )
